[CmdletBinding()]
param(
    [string]$ArtifactRoot,
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-LatestArtifactRoot {
    param(
        [string]$ArtifactsDir
    )

    $candidates = Get-ChildItem -Path $ArtifactsDir -Directory -Filter 'installer-ci-*' |
        Sort-Object Name -Descending

    if (-not $candidates) {
        throw "No installer CI artifact directories were found under '$ArtifactsDir'."
    }

    return $candidates[0].FullName
}

function Require-Path {
    param(
        [string]$Path,
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Label was not found at '$Path'."
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$artifactsDir = Join-Path $repoRoot 'artifacts'

if (-not $ArtifactRoot) {
    $ArtifactRoot = Get-LatestArtifactRoot -ArtifactsDir $artifactsDir
}

$artifactRoot = (Resolve-Path $ArtifactRoot).Path
$payloadRoot = Join-Path $artifactRoot 'windows-installer'
$installerDir = Join-Path $payloadRoot 'installer'
$exePath = Join-Path $payloadRoot 'AICodeReviewer.exe'
$checksumPath = Join-Path $payloadRoot 'AICodeReviewer.exe.sha256'

Require-Path -Path $payloadRoot -Label 'Extracted installer payload directory'
Require-Path -Path $installerDir -Label 'Installer subdirectory'
Require-Path -Path $exePath -Label 'Packaged EXE'
Require-Path -Path $checksumPath -Label 'Packaged checksum file'

$installer = Get-ChildItem -Path $installerDir -Filter 'AICodeReviewer-Setup-*.exe' | Select-Object -First 1
if (-not $installer) {
    throw "No installer executable matching 'AICodeReviewer-Setup-*.exe' was found under '$installerDir'."
}

$checksumLine = (Get-Content -LiteralPath $checksumPath | Select-Object -First 1).Trim()
if (-not $checksumLine) {
    throw "Checksum file '$checksumPath' was empty."
}

$expectedHash = ($checksumLine -split '\s+')[0].ToUpperInvariant()
$exeHash = (Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash.ToUpperInvariant()
$installerHash = (Get-FileHash -LiteralPath $installer.FullName -Algorithm SHA256).Hash.ToUpperInvariant()
$checksumMatches = $expectedHash -eq $exeHash

$exeVersion = (Get-Item -LiteralPath $exePath).VersionInfo
$installerVersion = (Get-Item -LiteralPath $installer.FullName).VersionInfo
$exeSignature = Get-AuthenticodeSignature -FilePath $exePath
$installerSignature = Get-AuthenticodeSignature -FilePath $installer.FullName

$runId = $null
$artifactDirName = Split-Path -Path $artifactRoot -Leaf
if ($artifactDirName -match '^installer-ci-(\d+)$') {
    $runId = $Matches[1]
}

$result = [pscustomobject]@{
    ArtifactRoot = $artifactRoot
    WorkflowRunId = $runId
    ExePath = $exePath
    ChecksumPath = $checksumPath
    InstallerPath = $installer.FullName
    ChecksumLine = $checksumLine
    ExpectedExeSha256 = $expectedHash
    ActualExeSha256 = $exeHash
    ExeChecksumMatches = $checksumMatches
    InstallerSha256 = $installerHash
    ExeFileVersion = $exeVersion.FileVersion
    ExeProductVersion = $exeVersion.ProductVersion
    ExeSignatureStatus = $exeSignature.Status.ToString()
    InstallerFileVersion = $installerVersion.FileVersion
    InstallerProductVersion = $installerVersion.ProductVersion
    InstallerSignatureStatus = $installerSignature.Status.ToString()
}

if ($Json) {
    $result | ConvertTo-Json -Depth 3
} else {
    $result | Format-List | Out-String
}

if (-not $checksumMatches) {
    exit 1
}