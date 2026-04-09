[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$FilePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-SignToolPath {
    if ($env:WINDOWS_SIGNTOOL_PATH) {
        if (-not (Test-Path -LiteralPath $env:WINDOWS_SIGNTOOL_PATH)) {
            throw "WINDOWS_SIGNTOOL_PATH was set but does not exist: $($env:WINDOWS_SIGNTOOL_PATH)"
        }
        return (Resolve-Path -LiteralPath $env:WINDOWS_SIGNTOOL_PATH).Path
    }

    $command = Get-Command signtool.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) {
        return $command.Source
    }

    $kitRoots = @(
        (Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'),
        (Join-Path $env:ProgramFiles 'Windows Kits\10\bin')
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

    $candidates = foreach ($root in $kitRoots) {
        Get-ChildItem -Path $root -Filter signtool.exe -Recurse -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending
    }

    $preferred = $candidates | Where-Object { $_.FullName -match '\\x64\\' } | Select-Object -First 1
    if ($preferred) {
        return $preferred.FullName
    }

    $fallback = $candidates | Select-Object -First 1
    if ($fallback) {
        return $fallback.FullName
    }

    throw 'signtool.exe was not found. Install the Windows SDK or set WINDOWS_SIGNTOOL_PATH.'
}

$resolvedFile = (Resolve-Path -LiteralPath $FilePath).Path
$certPath = $env:WINDOWS_SIGN_CERT_PATH

if ([string]::IsNullOrWhiteSpace($certPath)) {
    Write-Host "Skipping signing for '$resolvedFile' because WINDOWS_SIGN_CERT_PATH is not configured."
    exit 0
}

$resolvedCertPath = (Resolve-Path -LiteralPath $certPath).Path
$signTool = Get-SignToolPath
$timestampUrl = $env:WINDOWS_SIGN_TIMESTAMP_URL
if ([string]::IsNullOrWhiteSpace($timestampUrl)) {
    $timestampUrl = 'https://timestamp.digicert.com'
}

$arguments = @(
    'sign'
    '/fd', 'SHA256'
    '/td', 'SHA256'
    '/tr', $timestampUrl
    '/f', $resolvedCertPath
)

if (-not [string]::IsNullOrWhiteSpace($env:WINDOWS_SIGN_CERT_PASSWORD)) {
    $arguments += @('/p', $env:WINDOWS_SIGN_CERT_PASSWORD)
}

$arguments += $resolvedFile

Write-Host "Signing '$resolvedFile' with '$signTool'..."
& $signTool @arguments
if ($LASTEXITCODE -ne 0) {
    throw "signtool.exe failed with exit code $LASTEXITCODE while signing '$resolvedFile'."
}

$signature = Get-AuthenticodeSignature -FilePath $resolvedFile
Write-Host "Signature status for '$resolvedFile': $($signature.Status)"