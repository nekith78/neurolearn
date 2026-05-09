# install.ps1 — bootstrap installer for Windows
param(
    [string]$InstallMethod = "plugin"  # plugin | skill | cli
)

$ErrorActionPreference = "Stop"

Write-Host "==> Checking for uv..." -ForegroundColor Cyan
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv..." -ForegroundColor Yellow
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

Write-Host "==> Syncing dependencies..." -ForegroundColor Cyan
uv sync

Write-Host "==> Running wizard..." -ForegroundColor Cyan
uv run youtube-transcribe config wizard

Write-Host "==> Done!" -ForegroundColor Green
Write-Host "Try: uv run youtube-transcribe transcribe https://youtu.be/<id>"
