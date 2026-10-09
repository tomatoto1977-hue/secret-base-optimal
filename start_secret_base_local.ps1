# Secret Base Optimal local bridge launcher (PowerShell)
# Safe defaults: Claude Code and ComfyUI remain disabled.
# This script does not save tokens, change Render settings, or enable paid services.

$ErrorActionPreference = "Stop"
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw "Python 3.11+ is required. Install Python, then reopen PowerShell." }

if ([string]::IsNullOrWhiteSpace($env:SECRET_BASE_BRIDGE_TOKEN)) {
    Write-Host "Bridge token is not set. No network requests will be sent." -ForegroundColor Yellow
    Write-Host 'Set it for this PowerShell session only: $env:SECRET_BASE_BRIDGE_TOKEN = Read-Host "Bridge token"'
    exit 2
}
if ([string]::IsNullOrWhiteSpace($env:OBSIDIAN_VAULT_PATH) -or -not (Test-Path -LiteralPath $env:OBSIDIAN_VAULT_PATH -PathType Container)) {
    Write-Host "OBSIDIAN_VAULT_PATH must point to an existing local Obsidian vault." -ForegroundColor Yellow
    Write-Host 'Set it for this session: $env:OBSIDIAN_VAULT_PATH = Read-Host "Full path to Obsidian vault"'
    exit 2
}

if ([string]::IsNullOrWhiteSpace($env:ALLOW_CLAUDE_CODE)) { $env:ALLOW_CLAUDE_CODE = "false" }
if ([string]::IsNullOrWhiteSpace($env:ALLOW_LOCAL_COMFYUI)) { $env:ALLOW_LOCAL_COMFYUI = "false" }
if ([string]::IsNullOrWhiteSpace($env:SECRET_BASE_API)) { $env:SECRET_BASE_API = "https://secret-base-optimal-api.onrender.com" }

Write-Host "Claude Code enabled: $env:ALLOW_CLAUDE_CODE"
Write-Host "Local ComfyUI enabled: $env:ALLOW_LOCAL_COMFYUI"
Write-Host "Paid APIs and automatic publishing are not used by this worker."
if ($env:ALLOW_CLAUDE_CODE -eq "true") {
    Write-Warning "Claude Code may consume account usage. Confirm the account's limits before enabling."
}
if ($env:ALLOW_LOCAL_COMFYUI -eq "true") {
    Write-Warning "Local image generation may use substantial PC resources; no hosted image API is used."
}
python (Join-Path $PSScriptRoot "local_integration_worker.py")
