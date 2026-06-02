# start.ps1 — Arranca la Herramienta de Gestion desde la raiz del proyecto
# Uso: .\scripts\start.ps1  (o desde la raiz del proyecto: .\start.ps1 si fue copiado)
Set-Location (Resolve-Path "$PSScriptRoot\..")

$dump   = Join-Path (Get-Location) "deploy_db_backup.sql"
$marker = Join-Path (Get-Location) ".db_imported"

# Primera ejecucion: importar la base de datos del volcado incluido
if ((Test-Path $dump) -and (-not (Test-Path $marker))) {
    Write-Host "Primera ejecucion: importando base de datos..." -ForegroundColor Cyan
    docker compose up -d postgres
    Write-Host "Esperando a que PostgreSQL este listo (20 s)..." -ForegroundColor DarkGray

    $ready = $false
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Seconds 1
        $check = docker compose exec -T postgres pg_isready -U gestion 2>&1
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    }

    if (-not $ready) {
        Write-Warning "PostgreSQL no respondio a tiempo. Reintenta ejecutando start.ps1 de nuevo."
        exit 1
    }

    Get-Content $dump | docker compose exec -T postgres psql -U gestion gestion_db
    if ($LASTEXITCODE -eq 0) {
        New-Item -ItemType File -Path $marker -Force | Out-Null
        Write-Host "Base de datos importada correctamente." -ForegroundColor Green
    } else {
        Write-Warning "La importacion fallo. Revisa deploy_db_backup.sql e intentalo de nuevo."
        exit 1
    }
}

Write-Host "Arrancando todos los servicios..." -ForegroundColor Cyan
docker compose up -d

Write-Host ""
Write-Host "  Aplicacion disponible en: https://localhost" -ForegroundColor Green
Write-Host "  MailHog (dev):             http://localhost:18025" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Para detener: ejecuta scripts\stop.ps1" -ForegroundColor DarkGray
