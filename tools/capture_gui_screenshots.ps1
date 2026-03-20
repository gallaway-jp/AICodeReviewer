Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;

public struct RECT {
    public int Left;
    public int Top;
    public int Right;
    public int Bottom;
}

public static class NativeMethods {
    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
}
"@

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$launcher = Join-Path $repoRoot "tools\gui_screenshot_state.py"
$outputDir = Join-Path $repoRoot "docs\images"

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

function Save-WindowScreenshot {
    param(
        [Parameter(Mandatory = $true)] [System.Diagnostics.Process] $Process,
        [Parameter(Mandatory = $true)] [string] $OutputPath
    )

    $deadline = (Get-Date).AddSeconds(20)
    do {
        Start-Sleep -Milliseconds 300
        $Process.Refresh()
    } while ($Process.MainWindowHandle -eq 0 -and (Get-Date) -lt $deadline)

    if ($Process.MainWindowHandle -eq 0) {
        throw "Timed out waiting for GUI window"
    }

    Start-Sleep -Milliseconds 4500

    $rect = New-Object RECT
    [void][NativeMethods]::GetWindowRect($Process.MainWindowHandle, [ref] $rect)
    $width = $rect.Right - $rect.Left
    $height = $rect.Bottom - $rect.Top

    $bitmap = New-Object System.Drawing.Bitmap($width, $height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.CopyFromScreen($rect.Left, $rect.Top, 0, 0, $bitmap.Size)
    $bitmap.Save($OutputPath, [System.Drawing.Imaging.ImageFormat]::Png)
    $graphics.Dispose()
    $bitmap.Dispose()
}

$states = @(
    @{ State = "results"; File = "gui-results-tab.png" },
    @{ State = "ai-fix"; File = "gui-ai-fix-mode.png" }
)

foreach ($entry in $states) {
    Write-Host "Capturing $($entry.State) screenshot..."
    $process = Start-Process -FilePath $python -ArgumentList @($launcher, "--state", $entry.State, "--theme", "dark", "--lang", "en", "--hold-ms", "30000") -WorkingDirectory $repoRoot -PassThru
    try {
        Save-WindowScreenshot -Process $process -OutputPath (Join-Path $outputDir $entry.File)
    }
    finally {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force
        }
    }
}