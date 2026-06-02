# stop.ps1 — Detiene todos los contenedores de la Herramienta de Gestion
Set-Location (Resolve-Path "$PSScriptRoot\..")
Write-Host "Deteniendo servicios..." -ForegroundColor Cyan
docker compose down
Write-Host "Servicios detenidos." -ForegroundColor Green
