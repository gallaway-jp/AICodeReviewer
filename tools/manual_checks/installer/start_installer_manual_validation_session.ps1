[CmdletBinding()]
param(
    [string]$ArtifactRoot,
    [string]$RunId,
    [string]$Branch,
    [string]$Operator,
    [string]$OutputDir,
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$downloadScript = Join-Path $PSScriptRoot 'download_installer_artifact.ps1'
$inspectScript = Join-Path $PSScriptRoot 'inspect_installer_artifact.ps1'

if (($RunId -or $Branch) -and $ArtifactRoot) {
    throw 'Use either -ArtifactRoot or -RunId/-Branch, not both.'
}

$downloadResult = $null
if ($RunId -or $Branch) {
    $downloadArgs = @('-NoProfile', '-File', $downloadScript, '-Json')
    if ($RunId) {
        $downloadArgs += @('-RunId', $RunId)
    }
    if ($Branch) {
        $downloadArgs += @('-Branch', $Branch)
    }

    $downloadResult = & pwsh @downloadArgs | ConvertFrom-Json
    $ArtifactRoot = $downloadResult.ArtifactRoot
}

$inspectArgs = @('-NoProfile', '-File', $inspectScript, '-Json')
if ($ArtifactRoot) {
    $inspectArgs += @('-ArtifactRoot', $ArtifactRoot)
} elseif ($RunId) {
    $inspectArgs += @('-RunId', $RunId)
} elseif ($Branch) {
    $inspectArgs += @('-Branch', $Branch)
}

$artifact = & pwsh @inspectArgs | ConvertFrom-Json

if (-not $OutputDir) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $OutputDir = Join-Path $repoRoot "artifacts\manual-installer-validation-prep\$stamp"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$machineName = $env:COMPUTERNAME
$windowsVersion = try {
    (Get-ComputerInfo -Property WindowsProductName,WindowsVersion,OsBuildNumber -ErrorAction Stop |
        ForEach-Object { "$($_.WindowsProductName) $($_.WindowsVersion) (build $($_.OsBuildNumber))" })
} catch {
    $null
}
if (-not $windowsVersion) {
    $windowsVersion = [System.Environment]::OSVersion.VersionString
}

$effectiveBranch = ''
if ($downloadResult -and $downloadResult.PSObject.Properties['HeadBranch'] -and $downloadResult.HeadBranch) {
    $effectiveBranch = $downloadResult.HeadBranch
}

$effectiveCommit = ''
if ($downloadResult -and $downloadResult.PSObject.Properties['HeadSha'] -and $downloadResult.HeadSha) {
    $effectiveCommit = $downloadResult.HeadSha
}
$effectiveRunId = if ($artifact.WorkflowRunId) { $artifact.WorkflowRunId } else { '' }

$logPath = Join-Path $OutputDir 'validation-log.md'

$lines = @(
    '# Windows Installer Manual Validation Log'
    ''
    'Use this session log when validating a produced Windows installer artifact by hand.'
    ''
    '## Session Metadata'
    ''
    "- Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
    "- Operator: $Operator"
    "- Machine / Windows version: $machineName / $windowsVersion"
    "- Branch: $effectiveBranch"
    "- Commit: $effectiveCommit"
    "- Workflow run: $effectiveRunId"
    "- Artifact root: $($artifact.ArtifactRoot)"
    ''
    '## Artifact Preflight'
    ''
    ('- [x] Run pwsh -File tools/manual_checks/installer/inspect_installer_artifact.ps1 -ArtifactRoot {0}' -f $artifact.ArtifactRoot)
    "- Expected EXE SHA256: $($artifact.ExpectedExeSha256)"
    "- Actual EXE SHA256: $($artifact.ActualExeSha256)"
    "- EXE checksum match: $($artifact.ExeChecksumMatches)"
    "- Expected installer SHA256: $($artifact.ExpectedInstallerSha256)"
    "- Actual installer SHA256: $($artifact.InstallerSha256)"
    "- Installer checksum status: $($artifact.InstallerChecksumStatus)"
    "- EXE file version: $($artifact.ExeFileVersion)"
    "- EXE product version: $($artifact.ExeProductVersion)"
    "- EXE signature status: $($artifact.ExeSignatureStatus)"
    "- Installer file version: $($artifact.InstallerFileVersion)"
    "- Installer product version: $($artifact.InstallerProductVersion)"
    "- Installer signature status: $($artifact.InstallerSignatureStatus)"
    '- Preflight notes:'
    ''
    '## Install Validation'
    ''
    '- [ ] Installer launches successfully'
    '- [ ] Default install completes successfully'
    '- [ ] Files are installed under `Program Files\AICodeReviewer`'
    '- [ ] `config.ini` is present and matches the sanitized installer default'
    '- [ ] Start Menu GUI shortcut launches the desktop app'
    '- [ ] Start Menu CLI shortcut launches successfully'
    '- [ ] `AICodeReviewer.exe --help` runs from the install directory'
    '- Install notes:'
    ''
    '## Preserve-Data Uninstall Validation'
    ''
    '- [ ] Created or modified `config.ini`'
    '- [ ] Created or modified `aicodereviewer.log`'
    '- [ ] Created or modified `aicodereviewer-audit.log`'
    '- [ ] Uninstaller preserve-data option was selected'
    '- [ ] Data files remained after uninstall'
    '- Preserve-data notes:'
    ''
    '## Remove-Data Uninstall Validation'
    ''
    '- [ ] Reinstalled if needed for a second uninstall pass'
    '- [ ] Uninstaller remove-data option was selected'
    '- [ ] Data files were deleted after uninstall'
    '- Remove-data notes:'
    ''
    '## Warnings And User Experience'
    ''
    '- [ ] SmartScreen warning observed'
    '- [ ] Unsigned publisher warning observed'
    '- [ ] Unexpected permission/UAC issue observed'
    '- Warning details:'
    ''
    '## Suggested Commands'
    ''
    ('- Inspect again: pwsh -File tools/manual_checks/installer/inspect_installer_artifact.ps1 -ArtifactRoot {0}' -f $artifact.ArtifactRoot)
    ('- Current-user smoke pass: pwsh -File tools/manual_checks/installer/run_installer_smoke_validation.ps1 -ArtifactRoot {0} -InstallMode CurrentUser' -f $artifact.ArtifactRoot)
    ('- All-users smoke pass from an elevated shell: pwsh -File tools/manual_checks/installer/run_installer_smoke_validation.ps1 -ArtifactRoot {0} -InstallMode AllUsers' -f $artifact.ArtifactRoot)
    ''
    '## Result'
    ''
    '- Overall status:'
    '- Follow-up actions:'
)

$lines | Set-Content -LiteralPath $logPath -Encoding utf8

$result = [pscustomobject]@{
    ArtifactRoot = $artifact.ArtifactRoot
    WorkflowRunId = $effectiveRunId
    Branch = $effectiveBranch
    Commit = $effectiveCommit
    LogPath = $logPath
    OutputDir = (Resolve-Path $OutputDir).Path
}

if ($Json) {
    $result | ConvertTo-Json -Depth 3
} else {
    $result | Format-List | Out-String
}