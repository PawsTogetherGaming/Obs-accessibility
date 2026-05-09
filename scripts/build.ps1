# Builds a .nvda-addon file from c:\obs\addon\.
#
# An NVDA add-on is just a zip file with the .nvda-addon extension whose
# contents are at the root (manifest.ini, appModules\, readme, etc. — NOT
# wrapped in a parent directory). We zip the contents of addon\ and rename
# the result.
#
# Output: c:\obs\dist\obsAccessibility-<version>.nvda-addon
# Version is read from manifest.ini so the filename always matches.

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$addonDir = Join-Path $root "addon"
$distDir = Join-Path $root "dist"
$manifestPath = Join-Path $addonDir "manifest.ini"

if (-not (Test-Path $manifestPath)) {
    Write-Error "manifest.ini not found at $manifestPath"
    exit 1
}

# Parse version from manifest. Accepts either bare or quoted values.
$versionLine = Get-Content $manifestPath | Where-Object { $_ -match '^\s*version\s*=' } | Select-Object -First 1
if (-not $versionLine) {
    Write-Error "Could not find 'version =' line in manifest.ini"
    exit 1
}
$version = ($versionLine -replace '^\s*version\s*=\s*', '').Trim().Trim('"').Trim("'")
if (-not $version) {
    Write-Error "Could not parse version from: $versionLine"
    exit 1
}

# Sanity check: ADDON_VERSION in obs64.py should match manifest version.
$obsPyPath = Join-Path $addonDir "appModules\obs64.py"
$pyVersionLine = Get-Content $obsPyPath | Where-Object { $_ -match '^ADDON_VERSION\s*=' } | Select-Object -First 1
if ($pyVersionLine) {
    $pyVersion = ($pyVersionLine -replace '^ADDON_VERSION\s*=\s*', '').Trim().Trim('"').Trim("'")
    if ($pyVersion -ne $version) {
        Write-Warning "Version mismatch: manifest=$version, obs64.py ADDON_VERSION=$pyVersion"
    }
}

if (-not (Test-Path $distDir)) {
    New-Item -Path $distDir -ItemType Directory -Force | Out-Null
}

$baseName = "obsAccessibility-$version"
$zipPath = Join-Path $distDir "$baseName.zip"
$addonPath = Join-Path $distDir "$baseName.nvda-addon"

# Clear previous artifacts so we never ship stale bytes.
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
if (Test-Path $addonPath) { Remove-Item $addonPath -Force }

# Zip the *contents* of addon\, not the directory itself. Compress-Archive's
# -Path with a wildcard does this. Excludes any __pycache__ directories or
# .pyc files so we don't accidentally bundle compiled bytecode.
$items = Get-ChildItem -Path $addonDir -Force | Where-Object {
    $_.Name -ne "__pycache__"
}

if (-not $items) {
    Write-Error "addon\ directory is empty"
    exit 1
}

Compress-Archive -Path $items.FullName -DestinationPath $zipPath -CompressionLevel Optimal -Force

Move-Item -Path $zipPath -Destination $addonPath -Force

$size = (Get-Item $addonPath).Length
Write-Output "Built $addonPath ($size bytes)"
Write-Output "Install by opening the file with NVDA running."
