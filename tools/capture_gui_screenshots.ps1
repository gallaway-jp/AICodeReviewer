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

function Add-AnnotationOverlay {
    param(
        [Parameter(Mandatory = $true)] [string] $SourcePath,
        [Parameter(Mandatory = $true)] [string] $OutputPath,
        [Parameter(Mandatory = $true)] [array] $Annotations
    )

    $image = [System.Drawing.Image]::FromFile($SourcePath)
    try {
        $bitmap = New-Object System.Drawing.Bitmap($image)
    }
    finally {
        $image.Dispose()
    }

    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit

    $badgeFont = New-Object System.Drawing.Font("Segoe UI", 16, [System.Drawing.FontStyle]::Bold)
    $textFont = New-Object System.Drawing.Font("Segoe UI", 11, [System.Drawing.FontStyle]::Bold)
    $linePen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(230, 84, 190, 255), 3)
    $badgeBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(240, 25, 137, 224))
    $badgeTextBrush = [System.Drawing.Brushes]::White
    $boxBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(210, 16, 24, 32))
    $boxTextBrush = [System.Drawing.Brushes]::White
    $boxPen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(240, 84, 190, 255), 2)

    foreach ($annotation in $Annotations) {
        $badgeRect = New-Object System.Drawing.RectangleF($annotation.BadgeX, $annotation.BadgeY, 32, 32)
        $graphics.FillEllipse($badgeBrush, $badgeRect)
        $graphics.DrawEllipse($linePen, $badgeRect)

        $labelSize = $graphics.MeasureString($annotation.Label, $badgeFont)
        $labelX = $annotation.BadgeX + ((32 - $labelSize.Width) / 2)
        $labelY = $annotation.BadgeY + ((32 - $labelSize.Height) / 2) - 1
        $graphics.DrawString($annotation.Label, $badgeFont, $badgeTextBrush, $labelX, $labelY)

        $graphics.DrawLine($linePen, $annotation.LineStartX, $annotation.LineStartY, $annotation.LineEndX, $annotation.LineEndY)

        $textSize = $graphics.MeasureString($annotation.Text, $textFont)
        $boxRect = New-Object System.Drawing.RectangleF($annotation.TextX, $annotation.TextY, ($textSize.Width + 20), ($textSize.Height + 12))
        $graphics.FillRectangle($boxBrush, $boxRect)
        $graphics.DrawRectangle($boxPen, $boxRect.X, $boxRect.Y, $boxRect.Width, $boxRect.Height)
        $graphics.DrawString($annotation.Text, $textFont, $boxTextBrush, ($annotation.TextX + 10), ($annotation.TextY + 6))
    }

    try {
        $bitmap.Save($OutputPath, [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally {
        $graphics.Dispose()
        $bitmap.Dispose()
        $badgeFont.Dispose()
        $textFont.Dispose()
        $linePen.Dispose()
        $badgeBrush.Dispose()
        $boxBrush.Dispose()
        $boxPen.Dispose()
    }
}

$states = @(
    @{ State = "review"; File = "gui-review-tab.png" },
    @{ State = "review-partial"; File = "gui-review-partial-project.png" },
    @{ State = "results"; File = "gui-results-tab.png" },
    @{ State = "ai-fix"; File = "gui-ai-fix-mode.png" },
    @{ State = "log"; File = "gui-output-log-tab.png" },
    @{ State = "benchmarks"; File = "gui-benchmarks-tab.png" },
    @{ State = "benchmark-detached"; File = "gui-detached-benchmark-window.png" }
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

Add-AnnotationOverlay -SourcePath (Join-Path $outputDir "gui-review-partial-project.png") -OutputPath (Join-Path $outputDir "gui-review-partial-project.png") -Annotations @(
    [pscustomobject]@{ Label = "1"; BadgeX = 414; BadgeY = 637; LineStartX = 430; LineStartY = 653; LineEndX = 470; LineEndY = 653; TextX = 72; TextY = 620; Text = "Selected-file mode" },
    [pscustomobject]@{ Label = "2"; BadgeX = 696; BadgeY = 636; LineStartX = 712; LineStartY = 652; LineEndX = 662; LineEndY = 652; TextX = 596; TextY = 620; Text = "Focused file count" },
    [pscustomobject]@{ Label = "3"; BadgeX = 150; BadgeY = 730; LineStartX = 166; LineStartY = 746; LineEndX = 286; LineEndY = 746; TextX = 34; TextY = 712; Text = "Enable diff filtering" },
    [pscustomobject]@{ Label = "4"; BadgeX = 666; BadgeY = 804; LineStartX = 682; LineStartY = 820; LineEndX = 624; LineEndY = 820; TextX = 532; TextY = 786; Text = "Commit-range filter" }
)

Add-AnnotationOverlay -SourcePath (Join-Path $outputDir "gui-benchmarks-tab.png") -OutputPath (Join-Path $outputDir "gui-benchmarks-workflow.png") -Annotations @(
    [pscustomobject]@{ Label = "1"; BadgeX = 640; BadgeY = 873; LineStartX = 656; LineStartY = 889; LineEndX = 700; LineEndY = 905; TextX = 508; TextY = 820; Text = "Load the primary summary" },
    [pscustomobject]@{ Label = "2"; BadgeX = 642; BadgeY = 948; LineStartX = 658; LineStartY = 964; LineEndX = 702; LineEndY = 982; TextX = 490; TextY = 989; Text = "Load the comparison summary" },
    [pscustomobject]@{ Label = "3"; BadgeX = 92; BadgeY = 1115; LineStartX = 124; LineStartY = 1131; LineEndX = 240; LineEndY = 1131; TextX = 28; TextY = 1072; Text = "Triage fixture churn here" },
    [pscustomobject]@{ Label = "4"; BadgeX = 640; BadgeY = 1340; LineStartX = 656; LineStartY = 1356; LineEndX = 590; LineEndY = 1356; TextX = 520; TextY = 1300; Text = "Open previews and diffs" }
)