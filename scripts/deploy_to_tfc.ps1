<#
.SYNOPSIS
    Despliega la Herramienta de Gestión al usuario tfc en C:\Users\tfc\Documents.
.DESCRIPTION
    1. Verifica que el usuario destino existe
    2. Exporta la base de datos PostgreSQL (si Docker está activo)
    3. Copia todos los archivos de la aplicación
    4. Copia .env y certs/ (secretos y certificados TLS)
    5. Genera start.ps1 y stop.ps1 en el directorio destino
.PARAMETER DestUser
    Nombre del usuario Windows destino (default: tfc).
.EXAMPLE
    .\scripts\deploy_to_tfc.ps1
    .\scripts\deploy_to_tfc.ps1 -DestUser tfc
#>

param(
    [string]$DestUser = "tfc"
)

$ErrorActionPreference = "Stop"

# Raíz del proyecto (un nivel arriba de scripts/)
$Src  = (Resolve-Path "$PSScriptRoot\..").Path
$Dest = "C:\Users\$DestUser\Documents\Herramienta-de-gestion"

function Write-Step { param([string]$n, [string]$Msg) Write-Host "`n[$n] $Msg" -ForegroundColor Cyan }
function Write-OK   { param([string]$Msg) Write-Host "      OK  $Msg" -ForegroundColor Green }
function Write-Warn { param([string]$Msg) Write-Host "   AVISO  $Msg" -ForegroundColor Yellow }

# ─────────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Herramienta de Gestion -- Despliegue a usuario $DestUser" -ForegroundColor Cyan
Write-Host "  Origen : $Src"
Write-Host "  Destino: $Dest"
Write-Host ""

# ── 1. Verificar usuario destino ─────────────────────────────────────────────
Write-Step "1/5" "Verificando usuario destino..."
if (-not (Test-Path "C:\Users\$DestUser")) {
    Write-Error "El usuario '$DestUser' no existe en este equipo (no se encontro C:\Users\$DestUser)."
}
Write-OK "Usuario '$DestUser' encontrado."

# ── 2. Preparar directorio destino ───────────────────────────────────────────
Write-Step "2/5" "Preparando directorio destino..."
New-Item -ItemType Directory -Path "$Dest\logs" -Force | Out-Null
New-Item -ItemType Directory -Path "$Dest\certs" -Force | Out-Null
Write-OK "Directorio listo: $Dest"

# ── 3. Exportar base de datos ─────────────────────────────────────────────────
Write-Step "3/5" "Exportando base de datos PostgreSQL..."
$DbDump = "$Dest\deploy_db_backup.sql"

$postgresRunning = $false
try {
    Push-Location $Src
    $status = docker compose ps --services --filter "status=running" 2>&1
    if ($LASTEXITCODE -eq 0 -and ($status -match "postgres")) {
        $postgresRunning = $true
    }
    Pop-Location
} catch {
    try { Pop-Location } catch {}
}

if ($postgresRunning) {
    Push-Location $Src
    docker compose exec -T postgres pg_dump -U gestion --no-password gestion_db |
        Out-File -FilePath $DbDump -Encoding utf8
    $rc = $LASTEXITCODE
    Pop-Location
    if ($rc -ne 0) {
        Write-Warn "pg_dump finalizo con codigo $rc. El volcado puede estar incompleto."
    } else {
        $size = "{0:N0}" -f (Get-Item $DbDump).Length
        Write-OK "Base de datos exportada ($size bytes) -> deploy_db_backup.sql"
    }
} else {
    Write-Warn "PostgreSQL no esta en marcha."
    Write-Warn "Arranca 'docker compose up -d' y vuelve a ejecutar este script para incluir los datos."
    Write-Warn "Sin volcado, el usuario $DestUser arrancara con una BD vacia."
}

# ── 4. Copiar archivos de la aplicacion ──────────────────────────────────────
Write-Step "4/5" "Copiando archivos de la aplicacion..."

$excludeDirs = @(
    "__pycache__", ".git", "venv", ".venv", "env", ".pytest_cache",
    "htmlcov", "instance", "Mejoras", "ELIMINAR",
    "Entrega_borradores_Jaime_Walden", "node_modules"
)
$excludeFiles = @(
    "*.pyc", "*.pyo", ".coverage", "coverage.xml",
    "~$*", "Guia_de_Usuario*.docx",
    "TFC_Herramienta_Gestion_Remota_Windows_Jaime_Walden.docx",
    "Libro*.xlsx", "_guia_tmp.txt", "debug.py", "count_code_lines.py"
)

# Robocopy: /E=subdirectorios vacíos incluidos | /R:2 /W:1=reintentos
# Códigos de salida: 0=sin cambios, 1-7=ok con advertencias, >=8=error
$rcArgs = @($Src, $Dest, "/E", "/DCOPY:DA", "/R:2", "/W:1", "/NP", "/NFL", "/NDL",
            "/XD") + $excludeDirs + @("/XF") + $excludeFiles
& robocopy @rcArgs | Out-Null
if ($LASTEXITCODE -ge 8) {
    Write-Error "Robocopy fallo con codigo $LASTEXITCODE."
}
Write-OK "Archivos de la aplicacion copiados."

# Copiar .env (fuera del control de git — contiene secretos)
$envSrc = "$Src\.env"
if (Test-Path $envSrc) {
    Copy-Item $envSrc "$Dest\.env" -Force
    Write-OK ".env copiado (incluye SECRET_KEY y FIELD_ENCRYPTION_KEY)."
} else {
    Write-Warn ".env no encontrado en origen."
    Write-Warn "El usuario $DestUser debera crear $Dest\.env desde .env.example antes de arrancar."
}

# Copiar certificados TLS (certs/ esta en .gitignore — copiar explicitamente)
$certsSrc = "$Src\certs"
if ((Test-Path "$certsSrc\server.crt") -and (Test-Path "$certsSrc\server.key")) {
    Copy-Item "$certsSrc\server.crt" "$Dest\certs\server.crt" -Force
    Copy-Item "$certsSrc\server.key" "$Dest\certs\server.key" -Force
    Write-OK "Certificados TLS copiados (certs/server.crt y server.key)."
} else {
    Write-Warn "No se encontraron certificados TLS en $certsSrc."
    Write-Warn "El usuario $DestUser debera generarlos (ver README.md)."
}

# Copiar certificado del servidor PowerShell si existe
$psCert = "$Src\ps-server-cert.pem"
if (Test-Path $psCert) {
    Copy-Item $psCert "$Dest\ps-server-cert.pem" -Force
    Write-OK "Certificado TLS de PowerShell copiado."
}

# ── 5. Generar scripts de operacion para el usuario destino ──────────────────
Write-Step "5/5" "Generando scripts de operacion..."

# --- start.ps1 ---
$startContent = @'
# start.ps1 — Arranca la Herramienta de Gestion
# Ejecucion: clic derecho -> "Ejecutar con PowerShell", o desde terminal: .\start.ps1
Set-Location $PSScriptRoot

$dump   = Join-Path $PSScriptRoot "deploy_db_backup.sql"
$marker = Join-Path $PSScriptRoot ".db_imported"

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
Write-Host "  Para detener: ejecuta stop.ps1" -ForegroundColor DarkGray
'@
$startContent | Out-File -FilePath "$Dest\start.ps1" -Encoding utf8
Write-OK "start.ps1 generado."

# --- stop.ps1 ---
$stopContent = @'
# stop.ps1 — Detiene todos los contenedores de la Herramienta de Gestion
Set-Location $PSScriptRoot
Write-Host "Deteniendo servicios..." -ForegroundColor Cyan
docker compose down
Write-Host "Servicios detenidos." -ForegroundColor Green
'@
$stopContent | Out-File -FilePath "$Dest\stop.ps1" -Encoding utf8
Write-OK "stop.ps1 generado."

# ── Resumen final ─────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  DESPLIEGUE COMPLETADO" -ForegroundColor Green
Write-Host ""
Write-Host "  Directorio destino: $Dest"
Write-Host ""
Write-Host "  Pasos para el usuario $DestUser`:"
Write-Host "    1. Asegurarse de tener Docker Desktop instalado y en marcha."
Write-Host "    2. Abrir PowerShell en: $Dest"
Write-Host "    3. Ejecutar: .\start.ps1"
Write-Host "       (en el primer arranque importa la BD automaticamente)"
Write-Host ""
if (-not (Test-Path "$Src\.env")) {
    Write-Host "  AVISO: Falta el .env. Copiarlo manualmente antes de arrancar." -ForegroundColor Yellow
}
if (Test-Path $DbDump) {
    Write-Host "  La BD se importara automaticamente en el primer inicio de start.ps1." -ForegroundColor DarkGray
} else {
    Write-Host "  AVISO: No hay volcado de BD. La aplicacion arrancara con BD vacia." -ForegroundColor Yellow
}
Write-Host ""
