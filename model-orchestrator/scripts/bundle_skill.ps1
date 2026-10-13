# Config lives in-skill under config/; nothing to copy from a parent repo.
# Kept so older docs that call bundle_skill.ps1 still exit cleanly.
param()

$ErrorActionPreference = "Stop"

$SkillRoot = Split-Path -Parent $PSScriptRoot
$ConfigDir = Join-Path $SkillRoot "config"
$CoreTemplate = Join-Path $ConfigDir "integrations.core.yaml"
$IntegrationsActive = Join-Path $ConfigDir "integrations.yaml"

if (-not (Test-Path $ConfigDir)) {
    Write-Error "Missing config directory: $ConfigDir"
}

if (Test-Path $CoreTemplate) {
    Copy-Item -Force $CoreTemplate $IntegrationsActive
    Write-Host "Reset integrations.yaml from integrations.core.yaml (core profile)."
}

Write-Host "Config is in-skill at $ConfigDir — no separate bundle step needed."
