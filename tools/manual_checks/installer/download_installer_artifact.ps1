[CmdletBinding()]
param(
    [string]$RunId,
    [string]$Branch,
    [string]$Repository = 'gallaway-jp/AICodeReviewer',
    [string]$Workflow = 'windows-installer.yml',
    [string]$ArtifactName = 'windows-installer',
    [string]$OutputDir,
    [switch]$Force,
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$env:GH_PAGER = ''

function Invoke-GhCommand {
    param(
        [string[]]$Arguments,
        [switch]$ExpectJson
    )

    $output = & gh @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "GitHub CLI command failed: gh $($Arguments -join ' ')"
    }

    if ($ExpectJson) {
        if (-not $output) {
            throw "GitHub CLI command returned no JSON output: gh $($Arguments -join ' ')"
        }
        return $output | ConvertFrom-Json
    }

    return $output
}

function Test-DownloadedArtifactLayout {
    param(
        [string]$ArtifactRoot
    )

    $payloadRoot = Join-Path $ArtifactRoot 'windows-installer'
    $exePath = Join-Path $payloadRoot 'AICodeReviewer.exe'
    $installerDir = Join-Path $payloadRoot 'installer'

    return (Test-Path -LiteralPath $payloadRoot) -and
        (Test-Path -LiteralPath $exePath) -and
        (Test-Path -LiteralPath $installerDir)
}

$null = Invoke-GhCommand -Arguments @('auth', 'status')

$resolvedRunId = $RunId
$selectedRun = $null

if (-not $resolvedRunId) {
    $runArgs = @(
        'run', 'list',
        '--workflow', $Workflow,
        '--limit', '20',
        '--json', 'databaseId,displayTitle,headBranch,headSha,status,conclusion,createdAt'
    )
    if ($Branch) {
        $runArgs += @('--branch', $Branch)
    }

    $runs = Invoke-GhCommand -Arguments $runArgs -ExpectJson
    $selectedRun = $runs |
        Where-Object { $_.status -eq 'completed' -and $_.conclusion -eq 'success' } |
        Select-Object -First 1

    if (-not $selectedRun) {
        $branchHint = if ($Branch) { " on branch '$Branch'" } else { '' }
        throw "No successful '$Workflow' workflow runs were found$branchHint."
    }

    $resolvedRunId = [string]$selectedRun.databaseId
}

if (-not $OutputDir) {
    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
    $OutputDir = Join-Path $repoRoot "artifacts\installer-ci-$resolvedRunId"
}

if ((Test-Path -LiteralPath $OutputDir) -and (-not $Force) -and (Test-DownloadedArtifactLayout -ArtifactRoot $OutputDir)) {
    $result = [pscustomobject]@{
        RunId = $resolvedRunId
        Repository = $Repository
        ArtifactName = $ArtifactName
        ArtifactRoot = (Resolve-Path $OutputDir).Path
        PayloadRoot = (Resolve-Path (Join-Path $OutputDir 'windows-installer')).Path
        ReusedExisting = $true
    }

    if ($Json) {
        $result | ConvertTo-Json -Depth 3
    } else {
        $result | Format-List | Out-String
    }
    exit 0
}

if (Test-Path -LiteralPath $OutputDir) {
    Remove-Item -LiteralPath $OutputDir -Recurse -Force
}
New-Item -ItemType Directory -Path $OutputDir | Out-Null

if (-not $selectedRun) {
    $selectedRun = Invoke-GhCommand -Arguments @(
        'run', 'view', $resolvedRunId,
        '--json', 'databaseId,displayTitle,headBranch,headSha,status,conclusion,createdAt'
    ) -ExpectJson
}

$artifactResponse = Invoke-GhCommand -Arguments @(
    'api', "repos/$Repository/actions/runs/$resolvedRunId/artifacts"
) -ExpectJson

$artifact = $artifactResponse.artifacts |
    Where-Object { $_.name -eq $ArtifactName -and (-not $_.expired) } |
    Select-Object -First 1

if (-not $artifact) {
    throw "Artifact '$ArtifactName' was not found for workflow run '$resolvedRunId'."
}

$zipPath = Join-Path $OutputDir "$ArtifactName.zip"
$payloadRoot = Join-Path $OutputDir 'windows-installer'

$token = (Invoke-GhCommand -Arguments @('auth', 'token')) | Out-String
$token = $token.Trim()
if (-not $token) {
    throw 'Could not retrieve a GitHub authentication token for artifact download.'
}

$artifactZipUri = "https://api.github.com/repos/$Repository/actions/artifacts/$($artifact.id)/zip"
$downloadHeaders = @{
    Authorization = "Bearer $token"
    Accept = 'application/vnd.github+json'
    'X-GitHub-Api-Version' = '2022-11-28'
}
Invoke-WebRequest -Headers $downloadHeaders -Uri $artifactZipUri -OutFile $zipPath

Expand-Archive -LiteralPath $zipPath -DestinationPath $payloadRoot -Force
Remove-Item -LiteralPath $zipPath -Force

if (-not (Test-DownloadedArtifactLayout -ArtifactRoot $OutputDir)) {
    throw "Downloaded artifact '$ArtifactName' for run '$resolvedRunId' did not contain the expected installer payload layout."
}

$result = [pscustomobject]@{
    RunId = $resolvedRunId
    Repository = $Repository
    ArtifactName = $ArtifactName
    ArtifactId = [string]$artifact.id
    HeadBranch = $selectedRun.headBranch
    HeadSha = $selectedRun.headSha
    ArtifactRoot = (Resolve-Path $OutputDir).Path
    PayloadRoot = (Resolve-Path $payloadRoot).Path
    ReusedExisting = $false
}

if ($Json) {
    $result | ConvertTo-Json -Depth 3
} else {
    $result | Format-List | Out-String
}