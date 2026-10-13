# Install model-orchestrator into ~/.cursor/skills (skill dir is also ORCHESTRATOR_ROOT).
param(
    [ValidateSet("core", "stack")]
    [Alias("Profile")]
    [string]$InstallProfile = "core"
)

$ErrorActionPreference = "Stop"

$SkillRoot = Split-Path -Parent $PSScriptRoot
$Dst = Join-Path $env:USERPROFILE ".cursor\skills\model-orchestrator"
$ConfigDir = Join-Path $SkillRoot "config"
$IntegrationsActive = Join-Path $ConfigDir "integrations.yaml"
$CoreTemplate = Join-Path $ConfigDir "integrations.core.yaml"
$StackTemplate = Join-Path $ConfigDir "integrations.stack.yaml"
$ProjectsExample = Join-Path $ConfigDir "projects.example.yaml"
$ProjectsLocal = Join-Path $ConfigDir "projects.yaml"

if (-not (Test-Path (Join-Path $SkillRoot "SKILL.md"))) {
    Write-Error "SKILL.md not found under: $SkillRoot"
}

$template = if ($InstallProfile -eq "stack") { $StackTemplate } else { $CoreTemplate }
if (-not (Test-Path $template)) {
    Write-Error "Missing profile template: $template"
}
Copy-Item -Force $template $IntegrationsActive

if (-not (Test-Path $ProjectsLocal)) {
    if (Test-Path $ProjectsExample) {
        Copy-Item -Force $ProjectsExample $ProjectsLocal
        Write-Host "Created config/projects.yaml from projects.example.yaml (edit local paths)."
    }
}

New-Item -ItemType Directory -Force -Path (Split-Path $Dst) | Out-Null
if (Test-Path $Dst) {
    Remove-Item -Recurse -Force $Dst
}
Copy-Item -Recurse -Force $SkillRoot $Dst

$pointer = Join-Path $Dst "ORCHESTRATOR_ROOT.txt"
Set-Content -Path $pointer -Value $SkillRoot -Encoding UTF8

$IntegrationsSkill = Join-Path $Dst "integrations.yaml"
Copy-Item -Force $IntegrationsActive $IntegrationsSkill

Write-Host "Installed skill to: $Dst"
Write-Host "InstallProfile: $InstallProfile"
Write-Host "ORCHESTRATOR_ROOT -> $SkillRoot"

$syncScript = Join-Path $SkillRoot "scripts\sync_budget.py"
Write-Host "Budget: run  python scripts/sync_budget.py  (Other Models % → config/budget.local.yaml)"
$py = Get-Command python -ErrorAction SilentlyContinue
if ($py -and (Test-Path $syncScript)) {
    try {
        Push-Location $SkillRoot
        & python $syncScript 2>&1 | ForEach-Object { Write-Host $_ }
        Pop-Location
    } catch {
        Write-Host "Budget sync skipped (non-fatal): $($_.Exception.Message)"
    }
}

Write-Host "Done. In Cursor: Agent chat → @model-orchestrator (or Skills)."
