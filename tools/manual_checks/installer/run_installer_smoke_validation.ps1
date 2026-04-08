[CmdletBinding()]
param(
    [string]$ArtifactRoot,
    [string]$RunId,
    [string]$Branch,
    [ValidateSet('Auto', 'CurrentUser', 'AllUsers')]
    [string]$InstallMode = 'Auto',
    [string]$InstallDir,
    [string]$LogDir
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Test-IsAdministrator {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Assert-ExitCodeZero {
    param(
        [System.Diagnostics.Process]$Process,
        [string]$StepName
    )

    if ($Process.ExitCode -ne 0) {
        throw "$StepName failed with exit code $($Process.ExitCode)."
    }
}

function Invoke-Executable {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$StepName,
        [string]$WorkingDirectory = $null,
        [string]$RedirectStandardOutput = $null,
        [string]$RedirectStandardError = $null
    )

    $processArgs = @{
        FilePath = $FilePath
        ArgumentList = $ArgumentList
        Wait = $true
        PassThru = $true
        NoNewWindow = $true
    }

    if ($WorkingDirectory) {
        $processArgs.WorkingDirectory = $WorkingDirectory
    }
    if ($RedirectStandardOutput) {
        $processArgs.RedirectStandardOutput = $RedirectStandardOutput
    }
    if ($RedirectStandardError) {
        $processArgs.RedirectStandardError = $RedirectStandardError
    }

    $process = Start-Process @processArgs
    Assert-ExitCodeZero -Process $process -StepName $StepName
}

function Test-PathExists {
    param(
        [string]$LiteralPath,
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $LiteralPath)) {
        throw "$Label was not found at '$LiteralPath'."
    }
}

function Test-PathMissing {
    param(
        [string]$LiteralPath,
        [string]$Label
    )

    if (Test-Path -LiteralPath $LiteralPath) {
        throw "$Label still exists at '$LiteralPath'."
    }
}

if (-not (Test-IsAdministrator)) {
    $isAdministrator = $false
} else {
    $isAdministrator = $true
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$inspectScript = Join-Path $PSScriptRoot 'inspect_installer_artifact.ps1'

if (($RunId -or $Branch) -and $ArtifactRoot) {
    throw 'Use either -ArtifactRoot or -RunId/-Branch, not both.'
}

if ($InstallMode -eq 'Auto') {
    if ($isAdministrator) {
        $effectiveInstallMode = 'AllUsers'
    } else {
        $effectiveInstallMode = 'CurrentUser'
    }
} else {
    $effectiveInstallMode = $InstallMode
}

if (($effectiveInstallMode -eq 'AllUsers') -and (-not $isAdministrator)) {
    throw 'AllUsers smoke validation requires an elevated PowerShell session. Re-run elevated or use -InstallMode CurrentUser.'
}

if (-not $InstallDir) {
    if ($effectiveInstallMode -eq 'AllUsers') {
        $InstallDir = Join-Path $env:ProgramFiles 'AICodeReviewer-Validation'
    } else {
        $InstallDir = Join-Path $env:LOCALAPPDATA 'Programs\AICodeReviewer-Validation'
    }
}

if (-not $LogDir) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $LogDir = Join-Path $repoRoot "artifacts\manual-installer-validation\$stamp"
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$inspectArgs = @{
    Json = $true
}
if ($ArtifactRoot) {
    $inspectArgs.ArtifactRoot = $ArtifactRoot
}
if ($RunId) {
    $inspectArgs.RunId = $RunId
}
if ($Branch) {
    $inspectArgs.Branch = $Branch
}

$artifactJson = & pwsh -File $inspectScript @inspectArgs | ConvertFrom-Json
$installerPath = $artifactJson.InstallerPath

Test-PathExists -LiteralPath $installerPath -Label 'Installer executable'

$installLog = Join-Path $LogDir 'install.log'
$preserveUninstallLog = Join-Path $LogDir 'uninstall-preserve.log'
$removeUninstallLog = Join-Path $LogDir 'uninstall-remove.log'
$cliHelpLog = Join-Path $LogDir 'cli-help.txt'
$cliHelpErrorLog = Join-Path $LogDir 'cli-help.stderr.txt'
$summaryPath = Join-Path $LogDir 'summary.md'

$exePath = Join-Path $InstallDir 'AICodeReviewer.exe'
$configPath = Join-Path $InstallDir 'config.ini'
$logPath = Join-Path $InstallDir 'aicodereviewer.log'
$auditLogPath = Join-Path $InstallDir 'aicodereviewer-audit.log'
$uninstallerPath = Join-Path $InstallDir 'unins000.exe'

$startMenuRoot = if ($effectiveInstallMode -eq 'AllUsers') { $env:ProgramData } else { $env:APPDATA }
$startMenuPrograms = Join-Path $startMenuRoot 'Microsoft\Windows\Start Menu\Programs'
$guiShortcut = Join-Path $startMenuPrograms 'AICodeReviewer.lnk'
$cliShortcut = Join-Path $startMenuPrograms 'AICodeReviewer CLI.lnk'

$installModeArg = if ($effectiveInstallMode -eq 'AllUsers') { '/ALLUSERS' } else { '/CURRENTUSER' }

if (Test-Path -LiteralPath $uninstallerPath) {
    Invoke-Executable -FilePath $uninstallerPath -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/REMOVEUSERDATA', "/LOG=$LogDir\preclean-uninstall.log") -StepName 'Pre-clean uninstall'
}

if (Test-Path -LiteralPath $InstallDir) {
    Remove-Item -LiteralPath $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
}

Invoke-Executable -FilePath $installerPath -ArgumentList @('/SP-', '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', $installModeArg, "/DIR=$InstallDir", "/LOG=$installLog") -StepName 'Silent installer run'

Test-PathExists -LiteralPath $exePath -Label 'Installed EXE'
Test-PathExists -LiteralPath $configPath -Label 'Installed config'
Test-PathExists -LiteralPath $uninstallerPath -Label 'Installed uninstaller'
Test-PathExists -LiteralPath $guiShortcut -Label 'Start Menu GUI shortcut'
Test-PathExists -LiteralPath $cliShortcut -Label 'Start Menu CLI shortcut'

$guiShortcutPresentAfterInstall = $true
$cliShortcutPresentAfterInstall = $true

Invoke-Executable -FilePath $exePath -ArgumentList @('--help') -StepName 'CLI help validation' -WorkingDirectory $InstallDir -RedirectStandardOutput $cliHelpLog -RedirectStandardError $cliHelpErrorLog

Set-Content -LiteralPath $configPath -Value "[backend]`nprovider=local`n" -Encoding ascii
Set-Content -LiteralPath $logPath -Value 'installer preserve-data smoke log' -Encoding utf8
Set-Content -LiteralPath $auditLogPath -Value 'installer preserve-data smoke audit log' -Encoding utf8

Invoke-Executable -FilePath $uninstallerPath -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/PRESERVEUSERDATA', "/LOG=$preserveUninstallLog") -StepName 'Preserve-data uninstall'

Test-PathExists -LiteralPath $configPath -Label 'Preserved config'
Test-PathExists -LiteralPath $logPath -Label 'Preserved application log'
Test-PathExists -LiteralPath $auditLogPath -Label 'Preserved audit log'

Invoke-Executable -FilePath $installerPath -ArgumentList @('/SP-', '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', $installModeArg, "/DIR=$InstallDir", "/LOG=$LogDir\reinstall.log") -StepName 'Silent reinstall'

Test-PathExists -LiteralPath $uninstallerPath -Label 'Reinstalled uninstaller'
Set-Content -LiteralPath $configPath -Value "[backend]`nprovider=local`nmode=reset`n" -Encoding ascii
Set-Content -LiteralPath $logPath -Value 'installer remove-data smoke log' -Encoding utf8
Set-Content -LiteralPath $auditLogPath -Value 'installer remove-data smoke audit log' -Encoding utf8

Invoke-Executable -FilePath $uninstallerPath -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/REMOVEUSERDATA', "/LOG=$removeUninstallLog") -StepName 'Remove-data uninstall'

Test-PathMissing -LiteralPath $configPath -Label 'Removed config'
Test-PathMissing -LiteralPath $logPath -Label 'Removed application log'
Test-PathMissing -LiteralPath $auditLogPath -Label 'Removed audit log'

$summary = @(
    '# Installer Smoke Validation Summary'
    ''
    "- Artifact root: $($artifactJson.ArtifactRoot)"
    "- Workflow run: $($artifactJson.WorkflowRunId)"
    "- Install mode: $effectiveInstallMode"
    "- Installer path: $installerPath"
    "- Install directory: $InstallDir"
    "- EXE checksum match: $($artifactJson.ExeChecksumMatches)"
    "- Installer checksum status: $($artifactJson.InstallerChecksumStatus)"
    "- EXE file version: $($artifactJson.ExeFileVersion)"
    "- EXE product version: $($artifactJson.ExeProductVersion)"
    "- EXE signature status: $($artifactJson.ExeSignatureStatus)"
    "- Installer signature status: $($artifactJson.InstallerSignatureStatus)"
    "- GUI shortcut present after install: $guiShortcutPresentAfterInstall"
    "- CLI shortcut present after install: $cliShortcutPresentAfterInstall"
    '- Preserve-data uninstall: passed'
    '- Remove-data uninstall: passed'
    ''
    'Logs:'
    "- $installLog"
    "- $preserveUninstallLog"
    "- $removeUninstallLog"
    "- $cliHelpLog"
    "- $cliHelpErrorLog"
 )

$summary | Set-Content -LiteralPath $summaryPath -Encoding utf8
Write-Output "Smoke validation completed successfully. Summary: $summaryPath"