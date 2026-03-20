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
$pythonw = Join-Path $repoRoot ".venv\Scripts\pythonw.exe"
$python = if (Test-Path $pythonw) { $pythonw } else { Join-Path $repoRoot ".venv\Scripts\python.exe" }
$launcher = Join-Path $repoRoot "tools\gui_screenshot_state.py"
$outputDir = Join-Path $repoRoot "docs\images"

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

function Save-WindowScreenshot {
    param(
        [Parameter(Mandatory = $true)] [IntPtr] $WindowHandle,
        [Parameter(Mandatory = $true)] [string] $OutputPath
    )

    Start-Sleep -Milliseconds 4500

    $rect = New-Object RECT
    [void][NativeMethods]::GetWindowRect($WindowHandle, [ref] $rect)
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
    @{ State = "review"; File = "gui-review-tab.png" },
    @{ State = "results"; File = "gui-results-tab.png" },
    @{ State = "ai-fix"; File = "gui-ai-fix-mode.png" },
    @{ State = "log"; File = "gui-output-log-tab.png" }
)

foreach ($entry in $states) {
    Write-Host "Capturing $($entry.State) screenshot..."
    $hwndFile = Join-Path $env:TEMP ("aicodereviewer-gui-{0}-{1}.txt" -f $entry.State, [guid]::NewGuid().ToString("N"))
    $process = Start-Process -FilePath $python -ArgumentList @($launcher, "--state", $entry.State, "--theme", "dark", "--lang", "en", "--hold-ms", "30000", "--hwnd-file", $hwndFile) -WorkingDirectory $repoRoot -PassThru
    try {
        $deadline = (Get-Date).AddSeconds(20)
        do {
            Start-Sleep -Milliseconds 250
        } while (-not (Test-Path $hwndFile) -and (Get-Date) -lt $deadline)

        if (-not (Test-Path $hwndFile)) {
            throw "Timed out waiting for GUI window handle file"
        }

        $hwndText = Get-Content -Path $hwndFile -Raw
        $hwnd = [IntPtr]::new([int64]$hwndText.Trim())
        Save-WindowScreenshot -WindowHandle $hwnd -OutputPath (Join-Path $outputDir $entry.File)
    }
    finally {
        if (Test-Path $hwndFile) {
            [System.IO.File]::Delete($hwndFile)
        }
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force
        }
    }
}