# Copies the OBS accessibility app module into NVDA's scratchpad directory.
# After running, press NVDA+Ctrl+F3 in NVDA to reload plugins.

$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $root "addon\appModules\obs64.py"
$targetDir = Join-Path $env:APPDATA "nvda\scratchpad\appModules"

if (-not (Test-Path $source)) {
    Write-Error "Source not found: $source"
    exit 1
}

if (-not (Test-Path $targetDir)) {
    New-Item -Path $targetDir -ItemType Directory -Force | Out-Null
    Write-Output "Created $targetDir"
}

Copy-Item -Path $source -Destination $targetDir -Force
Write-Output "Deployed obs64.py to $targetDir"
Write-Output "In NVDA, press NVDA+Ctrl+F3 to reload plugins."
