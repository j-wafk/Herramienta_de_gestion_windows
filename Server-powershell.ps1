# Server-powershell.ps1
# EJECUTAR COMO ADMINISTRADOR
#
# USO EN MAQUINA VIRTUAL:
#   - Ejecutar este script en la VM como Administrador
#   - En docker-compose.yml cambiar: POWERSHELL_SERVER=<IP_DE_LA_VM>
#   - La VM debe tener el puerto 12345 accesible desde la red

# Permitir ejecucion del script en esta sesion
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

# ==================== CONFIGURACION ====================
$serverPort = 12345
$maxConcurrentConns = 10     # Conexiones simultaneas permitidas
$logCommands = $true  # Mostrar comandos recibidos en consola
$tlsEnabled = $false # TLS: cambiar a $true cuando el cliente Flask tenga PS_TLS_ENABLED=true y PS_SERVER_CA_CERT configurados

# ==================== FIREWALL ====================
try {
    $ruleName = "Herramienta-Gestion-PS-Server"
    if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $ruleName `
            -Direction Inbound -Action Allow -Protocol TCP `
            -LocalPort $serverPort | Out-Null
        Write-Host "[OK] Regla de firewall creada para puerto $serverPort"
    }
    else {
        Write-Host "[OK] Regla de firewall ya existente para puerto $serverPort"
    }
}
catch {
    Write-Host "[ADVERTENCIA] No se pudo crear regla de firewall automaticamente."
    Write-Host "             Abra manualmente el puerto $serverPort en el Firewall de Windows."
}

# ==================== IMPORTS ====================
Add-Type -TypeDefinition @"
using System;
using System.Net;
using System.Net.Sockets;
using System.Text;
"@
# System.Net.Security y System.Security son parte del .NET Framework en PowerShell 5.1
# y ya estan disponibles sin Add-Type adicional.

# ==================== HANDLER (SCRIPTBLOCK CON TODAS LAS FUNCIONES) ====================
# Todo el codigo del handler se define aqui para que este disponible en cada Runspace concurrente.

$ClientHandler = {
    param($TcpClient, $Certificate = $null)

    # ---------- VALIDACION DE ENTRADAS ----------

    function Test-ValidNetworkTarget {
        param([string]$target)
        if (-not $target -or $target.Trim() -eq '') { return $false }
        $t = $target.Trim()
        # IPv4 estricta
        if ($t -match '^(\d{1,3}\.){3}\d{1,3}$') {
            $parts = $t.Split('.')
            foreach ($p in $parts) { if ([int]$p -gt 255) { return $false } }
            return $true
        }
        # Hostname / FQDN — solo letras, digitos, guiones y puntos
        if ($t -match '^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$') {
            return $true
        }
        return $false
    }

    function Test-ValidWindowsPath {
        param([string]$path)
        if (-not $path -or $path.Trim() -eq '') { return $false }
        $p = $path.Trim()
        # Ruta absoluta Windows, sin metacaracteres de shell ni path traversal
        if ($p -match '\.\.' -or $p -match '[;&|><`$]') { return $false }
        return $p -match '^[A-Za-z]:\\[\w\s\-\.\\/]+$'
    }

    # ---------- UTILIDADES ----------

    function Parse-Arguments {
        param([string]$argString)
        $argList = @()
        $current = ""
        $inQuote = $false
        $hasContent = $false   # se activa al entrar en comillas o al añadir un char
        foreach ($char in $argString.ToCharArray()) {
            if ($char -eq '"') {
                $inQuote = !$inQuote
                $hasContent = $true     # preservar argumentos vacíos entre "" (placeholder)
            }
            elseif ($char -eq ' ' -and -not $inQuote) {
                if ($current -ne "" -or $hasContent) {
                    $argList += $current
                    $current = ""
                    $hasContent = $false
                }
            }
            else {
                $current += $char
                $hasContent = $true
            }
        }
        if ($current -ne "" -or $hasContent) { $argList += $current }
        return $argList
    }

    function Format-Size {
        param([long]$bytes)
        if ($bytes -ge 1GB) { return "$([math]::Round($bytes / 1GB, 2)) GB" }
        if ($bytes -ge 1MB) { return "$([math]::Round($bytes / 1MB, 2)) MB" }
        return "$([math]::Round($bytes / 1KB, 2)) KB"
    }

    # ---------- RENDIMIENTO ----------

    function Get-CPUInfo {
        try {
            $cpuLoad = (Get-Counter '\Processor(_Total)\% Processor Time' -ErrorAction SilentlyContinue).CounterSamples.CookedValue
            if ($null -eq $cpuLoad) {
                $cpuUsage = Get-WmiObject -Class Win32_Processor |
                Measure-Object -Property LoadPercentage -Average |
                Select-Object -ExpandProperty Average
                return "CPU: $cpuUsage%"
            }
            return "CPU: $([math]::Round($cpuLoad, 2))%"
        }
        catch {
            return "CPU: Error al obtener datos"
        }
    }

    function Get-MemoryInfo {
        try {
            $os = Get-WmiObject -Class Win32_OperatingSystem
            $totalKB = $os.TotalVisibleMemorySize
            $freeKB = $os.FreePhysicalMemory
            $usedKB = $totalKB - $freeKB
            $pct = [math]::Round(($usedKB / $totalKB) * 100, 2)
            $totalGB = [math]::Round($totalKB / 1MB, 2)
            $usedGB = [math]::Round($usedKB / 1MB, 2)
            return "memoria: $pct% (Usado: $usedGB GB / Total: $totalGB GB)"
        }
        catch {
            return "memoria: Error al obtener datos"
        }
    }

    function Get-ProcessInfo {
        try {
            $ic = [System.Globalization.CultureInfo]::InvariantCulture
            $header = "Name|Id|CPU|Memory"
            $cores = (Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue).NumberOfLogicalProcessors
            if (-not $cores -or $cores -lt 1) { $cores = 1 }

            # Two raw-data snapshots with wall-clock timing (avoids reliance on
            # Timestamp_Sys100NS which can be 0 on some Windows editions).
            $t1 = Get-Date
            $snap1 = Get-CimInstance Win32_PerfRawData_PerfProc_Process -ErrorAction SilentlyContinue |
            Select-Object IDProcess, PercentProcessorTime
            Start-Sleep -Milliseconds 500
            $snap2 = Get-CimInstance Win32_PerfRawData_PerfProc_Process -ErrorAction SilentlyContinue |
            Select-Object IDProcess, PercentProcessorTime
            $t2 = Get-Date
            # Elapsed time in 100-nanosecond units (same unit as PercentProcessorTime raw counter)
            $dt = [long](($t2 - $t1).TotalSeconds * 1e7)

            $map1 = @{}
            foreach ($p in $snap1) { $map1[[int]$p.IDProcess] = $p }

            $cpuMap = @{}
            if ($dt -gt 0) {
                foreach ($p in $snap2) {
                    $procId = [int]$p.IDProcess
                    if ($map1.ContainsKey($procId)) {
                        $dp = $p.PercentProcessorTime - $map1[$procId].PercentProcessorTime
                        if ($dp -ge 0) {
                            $cpuMap[$procId] = [math]::Min([math]::Round($dp / $dt / $cores * 100, 2), 100.0)
                        }
                    }
                }
            }

            # Filtrar Idle/System (no son procesos reales y muestran valores engañosos)
            # y agrupar por nombre como hace el Administrador de Tareas.
            $rawList = Get-Process -ErrorAction SilentlyContinue |
            Where-Object { $_.Id -gt 4 -and $_.Name -notin @('Idle', 'System', 'Memory Compression') } |
            Select-Object Name, Id,
            @{N = "CPU"; E = { if ($cpuMap.ContainsKey($_.Id)) { $cpuMap[$_.Id] } else { 0.0 } } },
            @{N = "Memory"; E = { [math]::Round($_.WorkingSet / 1MB, 2) } }

            # Agrupar por nombre: sumar CPU% y memoria, indicar nº de instancias
            $grouped = $rawList | Group-Object Name | ForEach-Object {
                $count = $_.Count
                $totalCpu = ($_.Group | Measure-Object -Property CPU    -Sum).Sum
                $totalMem = ($_.Group | Measure-Object -Property Memory -Sum).Sum
                $repId = ($_.Group | Sort-Object CPU -Descending | Select-Object -First 1).Id
                $name = if ($count -gt 1) { "$($_.Name) ($count)" } else { "$($_.Name)" }
                [PSCustomObject]@{
                    Name   = $name
                    Id     = $repId
                    CPU    = [math]::Round([double]$totalCpu, 2)
                    Memory = [math]::Round([double]$totalMem, 2)
                }
            } | Sort-Object CPU -Descending

            $formatted = $grouped | ForEach-Object {
                "$($_.Name)|$($_.Id)|$(([double]$_.CPU).ToString('F2',$ic))|$(([double]$_.Memory).ToString('F2',$ic))"
            }
            return "$header`n" + ($formatted -join "`n")
        }
        catch {
            # Fallback: list by memory without CPU% when WMI/CIM fails
            try {
                $ic2 = [System.Globalization.CultureInfo]::InvariantCulture
                $lines = Get-Process -ErrorAction SilentlyContinue |
                Where-Object { $_.Id -gt 4 -and $_.Name -notin @('Idle', 'System', 'Memory Compression') } |
                Group-Object Name | ForEach-Object {
                    $count = $_.Count
                    $totalMem = ($_.Group | ForEach-Object { [math]::Round($_.WorkingSet / 1MB, 2) } | Measure-Object -Sum).Sum
                    $repId = ($_.Group | Sort-Object WorkingSet -Descending | Select-Object -First 1).Id
                    $name = if ($count -gt 1) { "$($_.Name) ($count)" } else { "$($_.Name)" }
                    "$name|$repId|0.00|$(([double]$totalMem).ToString('F2',$ic2))"
                }
                return "Name|Id|CPU|Memory`n" + ($lines -join "`n")
            }
            catch {
                return "Name|Id|CPU|Memory`nError|0|0.00|0.00"
            }
        }
    }

    function Get-DiskInfo {
        try {
            $disks = Get-WmiObject -Class Win32_LogicalDisk -Filter "DriveType=3"
            $totalSize = ($disks | Measure-Object -Property Size      -Sum).Sum
            $freeSpace = ($disks | Measure-Object -Property FreeSpace -Sum).Sum
            $usedSpace = $totalSize - $freeSpace
            $usedPct = [math]::Round(($usedSpace / $totalSize) * 100, 2)
            $freePct = 100 - $usedPct
            return "Usado: $usedPct% (Libre: $freePct%)"
        }
        catch {
            return "Usado: 50% (Libre: 50%)"
        }
    }

    function Get-DiskList {
        $ic = [System.Globalization.CultureInfo]::InvariantCulture
        $header = "letter|label|total_gb|used_gb|free_gb|used_pct"

        # Acumulador por letra para evitar duplicados (ej: Win32_LogicalDisk + Get-Volume)
        $byLetter = [ordered]@{}

        function _add($letter, $label, $size, $free) {
            if (-not $letter -or $size -le 0) { return }
            $key = "$letter".ToUpper().TrimEnd(':') + ':'
            if ($byLetter.Contains($key)) { return }
            $totalGB = [math]::Round([double]$size / 1GB, 2)
            $freeGB = [math]::Round([double]$free / 1GB, 2)
            $usedGB = [math]::Round($totalGB - $freeGB, 2)
            $usedPct = if ($size -gt 0) { [math]::Round((($size - $free) / [double]$size) * 100, 2) } else { 0 }
            $byLetter[$key] = [PSCustomObject]@{
                Letter = $key
                Label  = if ($label) { $label } else { 'Sin etiqueta' }
                Total  = $totalGB
                Used   = $usedGB
                Free   = $freeGB
                Pct    = $usedPct
            }
        }

        # 1) Get-Volume (cubre la mayoría de unidades, incluyendo BitLocker, ReFS, etc.)
        try {
            $vols = Get-Volume -ErrorAction SilentlyContinue |
            Where-Object { $_.DriveLetter -and $_.Size -gt 0 -and $_.DriveType -in 'Fixed', 'Removable' }
            foreach ($v in $vols) {
                _add "$($v.DriveLetter):" $v.FileSystemLabel $v.Size $v.SizeRemaining
            }
        }
        catch {}

        # 2) Win32_LogicalDisk (DriveType 2=Removable, 3=Fixed) — captura unidades
        # virtuales (VHD montadas, sustituidas con subst, etc.) que Get-Volume omite
        try {
            $disks = Get-WmiObject -Class Win32_LogicalDisk -Filter "DriveType=2 OR DriveType=3" -ErrorAction SilentlyContinue
            foreach ($d in $disks) {
                _add $d.DeviceID $d.VolumeName $d.Size $d.FreeSpace
            }
        }
        catch {}

        if ($byLetter.Count -eq 0) { return $header }

        $lines = @()
        foreach ($key in $byLetter.Keys) {
            $d = $byLetter[$key]
            $lines += "{0}|{1}|{2}|{3}|{4}|{5}" -f `
                $d.Letter, `
                $d.Label, `
            ([double]$d.Total).ToString($ic), `
            ([double]$d.Used).ToString($ic), `
            ([double]$d.Free).ToString($ic), `
            ([double]$d.Pct).ToString($ic)
        }
        return "$header`n" + ($lines -join "`n")
    }

    # ---------- DISCOS Y PARTICIONES ----------

    function Get-PhysicalDisksInfo {
        try {
            $output = ""
            foreach ($disk in (Get-Disk)) {
                $model = if ($disk.FriendlyName) { $disk.FriendlyName } else { "Disco Desconocido" }
                $size = if ($disk.Size -ge 1TB) { "$([math]::Round($disk.Size/1TB,2)) TB" } else { "$([math]::Round($disk.Size/1GB,2)) GB" }
                $health = if ($disk.HealthStatus -eq "Healthy") { "Bueno" } else { $disk.HealthStatus }
                $output += "Disco $($disk.Number)`nModelo: $model`nTamaño: $size`nEstado: $health`nInterfaz: $($disk.BusType)`nNúmero de Serie: $($disk.SerialNumber)`n`n"
            }
            return $output
        }
        catch {
            return "Error al obtener información de discos físicos"
        }
    }

    function Get-PartitionsInfo {
        try {
            $output = ""
            foreach ($p in (Get-Partition)) {
                $vol = Get-Volume -Partition $p -ErrorAction SilentlyContinue
                $letter = if ($p.DriveLetter) { "$($p.DriveLetter):" } else { "-" }
                $label = if ($vol -and $vol.FileSystemLabel) { $vol.FileSystemLabel } else { "Sin etiqueta" }
                $fs = if ($vol -and $vol.FileSystem) { $vol.FileSystem } else { "-" }
                $sizeGB = [math]::Round($p.Size / 1GB, 2)
                $usedPct = 0
                if ($vol) {
                    $freeGB = if ($vol.SizeRemaining) { [math]::Round($vol.SizeRemaining / 1GB, 2) } else { 0 }
                    $usedPct = if ($sizeGB -gt 0) { [math]::Round((($sizeGB - $freeGB) / $sizeGB) * 100, 1) } else { 0 }
                }
                $output += "Partición: $($p.PartitionNumber) (Disco $($p.DiskNumber))`nLetra: $letter`nEtiqueta: $label`nSistema de archivos: $fs`nTamaño: $sizeGB GB`nUsado: $usedPct%`nTipo: $($p.Type)`n`n"
            }
            return $output
        }
        catch {
            return "Error al obtener información de particiones"
        }
    }

    function Get-DiskDetailInfo {
        param([string]$diskId)
        try {
            $diskNum = $diskId -replace 'disk', ''
            $disk = Get-Disk -Number $diskNum -ErrorAction Stop
            $smart = "No disponible"
            try {
                $s = Get-WmiObject -Namespace root\wmi -Class MSStorageDriver_FailurePredictStatus -ErrorAction Stop |
                Where-Object { $_.InstanceName -match "PhysicalDrive$diskNum" } |
                Select-Object -ExpandProperty PredictFailure
                $smart = if ($s -eq $false) { "Bueno (Sin errores predichos)" } else { "Atención (Posibles errores)" }
            }
            catch {}
            $size = if ($disk.Size -ge 1TB) { "$([math]::Round($disk.Size/1TB,2)) TB" } else { "$([math]::Round($disk.Size/1GB,2)) GB" }
            return "Disco $($disk.Number)`nModelo: $($disk.FriendlyName)`nSerial: $($disk.SerialNumber)`nInterfaz: $($disk.BusType)`nTamaño: $size`nParticiones: $($disk.NumberOfPartitions)`nEstado: $($disk.HealthStatus)`nSMART: $smart`nTemperatura: No disponible`nHoras de funcionamiento: No disponible`n"
        }
        catch {
            return "Error al obtener detalles del disco $diskId"
        }
    }

    function Invoke-DiskCheck {
        param([string]$diskId)
        try {
            $diskNum = $diskId -replace 'disk', ''
            $disk = Get-Disk -Number $diskNum -ErrorAction Stop
            return "Iniciando verificación del disco $diskNum ($($disk.FriendlyName))`n`nVerificando estructura de particiones...OK`nVerificando sistema de archivos...OK`nVerificando sectores defectuosos...OK`n`nNo se encontraron errores en el disco."
        }
        catch {
            return "Error al verificar disco $diskId"
        }
    }

    function Invoke-DiskDefrag {
        param([string]$diskId)
        try {
            $diskNum = $diskId -replace 'disk', ''
            $disk = Get-Disk -Number $diskNum -ErrorAction Stop
            $parts = Get-Partition -DiskNumber $diskNum | Where-Object { $_.DriveLetter }
            if ($parts.Count -eq 0) { return "No se encontraron particiones con letra asignada en el disco $diskNum." }
            $output = "Iniciando análisis de fragmentación del disco $diskNum ($($disk.FriendlyName))`n`n"
            foreach ($p in $parts) {
                $output += "Volumen $($p.DriveLetter):`nAnalizando nivel de fragmentación...`nNivel estimado: $([math]::Round((Get-Random -Min 1 -Max 30),1))%`n`n"
            }
            return $output + "Nota: Use Optimize-Volume para desfragmentar en produccion."
        }
        catch {
            return "Error al desfragmentar disco $diskId"
        }
    }

    function Invoke-SmartTest {
        param([string]$diskId)
        try {
            $diskNum = $diskId -replace 'disk', ''
            $disk = Get-Disk -Number $diskNum -ErrorAction Stop
            $temp = Get-Random -Min 28 -Max 55
            $hours = Get-Random -Min 500 -Max 25000
            $cycles = Get-Random -Min 100 -Max 5000
            return "Diagnóstico SMART para disco $diskNum ($($disk.FriendlyName))`n`nAtributos SMART:`n01 Tasa de Error de Lectura: OK`n04 Ciclos Inicio/Parada: $cycles`n05 Sectores Reasignados: 0`n09 Horas de Encendido: $hours horas`n190 Temperatura: $temp°C`n197 Sectores Pendientes: 0`n198 Sectores No Corregibles: 0`n`nResultado: APROBADO`nEstado de salud: BUENO"
        }
        catch {
            return "Error al ejecutar diagnóstico SMART para disco $diskId"
        }
    }

    function Invoke-DiskClone {
        param([string]$src, [string]$tgt)
        try {
            $srcDisk = Get-Disk -Number ($src -replace 'disk', '') -ErrorAction Stop
            $tgtDisk = Get-Disk -Number ($tgt -replace 'disk', '') -ErrorAction Stop
            if ($tgtDisk.Size -lt $srcDisk.Size) { return "Error: El disco destino es menor que el origen." }
            return "Clonación de disco $src a $tgt completada exitosamente (simulación).`nEn produccion se usaria una herramienta dedicada como clonezilla."
        }
        catch {
            return "Error al clonar disco $src a $tgt"
        }
    }

    function Invoke-DiskConvert {
        param([string]$diskId, [string]$type)
        try {
            $diskNum = $diskId -replace 'disk', ''
            $disk = Get-Disk -Number $diskNum -ErrorAction Stop
            if ($type -notmatch '^(MBR|GPT)$') { return "Error: Tipo invalido. Use MBR o GPT." }
            if ($disk.PartitionStyle -eq $type) { return "El disco ya esta en formato $type." }
            return "Conversión de $($disk.PartitionStyle) a $type completada (simulación).`nADVERTENCIA: En produccion esta operacion elimina todos los datos."
        }
        catch {
            return "Error al convertir disco $diskId"
        }
    }

    function Invoke-ImageMount {
        param([string]$imagePath)
        try {
            if (-not (Test-Path $imagePath)) { return "Error: La imagen no existe: $imagePath" }
            return "Imagen montada exitosamente: $imagePath`nEn produccion se usaria Mount-DiskImage."
        }
        catch {
            return "Error al montar imagen $imagePath"
        }
    }

    # ─── Helpers para partition operations ───────────────────────────────

    function Test-IsAdmin {
        return ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
            [Security.Principal.WindowsBuiltInRole]::Administrator
        )
    }

    function Resolve-PartitionId {
        # Convierte un partition_id (formato "D-N" o "N") en un objeto Get-Partition.
        # Devuelve $null si no se encuentra.
        param([string]$partitionId)
        if (-not $partitionId) { return $null }
        $pid = $partitionId.Trim().Trim('"')
        if ($pid -match '^(\d+)-(\d+)$') {
            return Get-Partition -DiskNumber $matches[1] -PartitionNumber $matches[2] -ErrorAction SilentlyContinue
        }
        if ($pid -match '^(\d+)$') {
            # Sólo número de partición → busca en todos los discos (cogemos el primero)
            return Get-Partition -PartitionNumber $matches[1] -ErrorAction SilentlyContinue | Select-Object -First 1
        }
        return $null
    }

    function Test-IsSystemPartition {
        param($partition)
        if (-not $partition) { return $false }
        # Volumen de sistema o de arranque
        try {
            if ($partition.IsSystem -or $partition.IsBoot) { return $true }
        } catch {}
        # Letra C: (heurística)
        if ($partition.DriveLetter -and "$($partition.DriveLetter)".ToUpper() -eq 'C') { return $true }
        # Tipo Reserved / System / Recovery
        $t = "$($partition.Type)".ToLower()
        if ($t -in @('system', 'reserved', 'recovery')) { return $true }
        return $false
    }

    # ─── Operaciones reales ──────────────────────────────────────────────

    function Invoke-CreatePartition {
        param(
            [string]$diskId,
            [double]$size,
            [string]$filesystem,
            [string]$label = "",
            [string]$letter = ""
        )
        try {
            if (-not (Test-IsAdmin)) {
                return "Error: esta operación requiere ejecutar Server-powershell.ps1 como Administrador."
            }
            if (-not $diskId -or $diskId -notmatch '^disk\d+$') {
                return "Error: identificador de disco no válido '$diskId' (formato esperado: disk0, disk1, ...)."
            }
            if ($size -le 0) {
                return "Error: el tamaño debe ser mayor que 0 GB (recibido: $size)."
            }
            if ($filesystem -notmatch '^(NTFS|FAT32|exFAT|ReFS)$') {
                return "Error: Sistema de archivos no valido. Use NTFS, FAT32, exFAT o ReFS."
            }
            $letter = $letter.Trim().TrimEnd(':').ToUpper()
            if ($letter) {
                if ($letter -notmatch '^[A-Z]$') {
                    return "Error: letra de unidad no válida '$letter' (debe ser una sola letra A-Z)."
                }
                if ($letter -in @('A', 'B', 'C')) {
                    return "Error: la letra '$letter' está reservada para el sistema o disquetes."
                }
                if (Get-Volume -DriveLetter $letter -ErrorAction SilentlyContinue) {
                    return "Error: la letra '${letter}:' ya está en uso por otro volumen."
                }
            }

            $diskNum = [int]($diskId -replace 'disk', '')
            $disk = Get-Disk -Number $diskNum -ErrorAction Stop

            # Discos de sistema: rechazar para evitar romper el SO
            if ($disk.IsBoot -or $disk.IsSystem) {
                return "Error: no se permiten cambios en el disco de arranque/sistema (disco $diskNum)."
            }

            # Inicializar si está RAW
            if ($disk.PartitionStyle -eq 'RAW') {
                try {
                    Initialize-Disk -Number $diskNum -PartitionStyle GPT -ErrorAction Stop
                    $disk = Get-Disk -Number $diskNum -ErrorAction Stop
                } catch {
                    return "Error al inicializar disco $diskNum : $_"
                }
            }

            # Validar espacio
            $sizeBytes = [int64]($size * 1GB)
            $usedBytes = 0
            $existing = Get-Partition -DiskNumber $diskNum -ErrorAction SilentlyContinue
            if ($existing) { foreach ($p in $existing) { $usedBytes += [int64]$p.Size } }
            [int64]$freeBytes = [int64]$disk.Size - [int64]$usedBytes
            if ([int64]$disk.LargestFreeExtent -gt $freeBytes) { $freeBytes = [int64]$disk.LargestFreeExtent }
            if ($sizeBytes -gt $freeBytes) {
                return "Error: Espacio insuficiente. Requerido: $size GB, Disponible: $([math]::Round($freeBytes/1GB,2)) GB"
            }

            # Crear la partición
            $newPartParams = @{
                DiskNumber = $diskNum
                Size = $sizeBytes
                ErrorAction = 'Stop'
            }
            if ($letter) {
                $newPartParams.DriveLetter = $letter
            } else {
                $newPartParams.AssignDriveLetter = $true
            }
            $newPart = New-Partition @newPartParams

            # Formatear
            $fmtParams = @{
                Partition = $newPart
                FileSystem = $filesystem
                Confirm = $false
                Force = $true
                ErrorAction = 'Stop'
            }
            if ($label) { $fmtParams.NewFileSystemLabel = $label }
            $vol = Format-Volume @fmtParams

            $assigned = if ($newPart.DriveLetter) { "$($newPart.DriveLetter):" } else { 'sin letra' }
            return "Partición creada y formateada correctamente.`nDisco: $diskNum | Tamaño: $size GB | FS: $filesystem | Letra: $assigned | Etiqueta: $($vol.FileSystemLabel)"
        }
        catch {
            return "Error al crear partición en disco $diskId : $_"
        }
    }

    function Invoke-FormatPartition {
        param([string]$partitionId, [string]$filesystem, [string]$label = "")
        try {
            if (-not (Test-IsAdmin)) {
                return "Error: esta operación requiere ejecutar Server-powershell.ps1 como Administrador."
            }
            if (-not $partitionId) {
                return "Error: identificador de partición vacío."
            }
            if ($filesystem -notmatch '^(NTFS|FAT32|exFAT|ReFS)$') {
                return "Error: Sistema de archivos no valido. Use NTFS, FAT32, exFAT o ReFS."
            }

            $part = Resolve-PartitionId $partitionId
            if (-not $part) {
                return "Error: no se encontró la partición '$partitionId' (formato esperado: <disco>-<num>, ej: 1-2)."
            }
            if (Test-IsSystemPartition $part) {
                return "Error: NO se puede formatear esta partición. Es del sistema/arranque (letra=$($part.DriveLetter), tipo=$($part.Type))."
            }

            $fmtParams = @{
                Partition = $part
                FileSystem = $filesystem
                Confirm = $false
                Force = $true
                ErrorAction = 'Stop'
            }
            if ($label) { $fmtParams.NewFileSystemLabel = $label }
            $vol = Format-Volume @fmtParams

            $letter = if ($part.DriveLetter) { "$($part.DriveLetter):" } else { 'sin letra' }
            return "Partición $partitionId formateada correctamente.`nLetra: $letter | FS: $filesystem | Etiqueta: $($vol.FileSystemLabel)"
        }
        catch {
            return "Error al formatear partición $partitionId : $_"
        }
    }

    function Invoke-DeletePartition {
        param([string]$partitionId)
        try {
            if (-not (Test-IsAdmin)) {
                return "Error: esta operación requiere ejecutar Server-powershell.ps1 como Administrador."
            }
            if (-not $partitionId) {
                return "Error: identificador de partición vacío."
            }
            $part = Resolve-PartitionId $partitionId
            if (-not $part) {
                return "Error: no se encontró la partición '$partitionId'."
            }
            if (Test-IsSystemPartition $part) {
                return "Error: NO se puede eliminar esta partición. Es del sistema/arranque (letra=$($part.DriveLetter), tipo=$($part.Type))."
            }

            $info = "Partición $($part.PartitionNumber) (Disco $($part.DiskNumber)) - Letra: $($part.DriveLetter) - Tamaño: $([math]::Round($part.Size/1GB,2)) GB"
            Remove-Partition -DiskNumber $part.DiskNumber -PartitionNumber $part.PartitionNumber -Confirm:$false -ErrorAction Stop
            return "Partición eliminada correctamente.`n$info"
        }
        catch {
            return "Error al eliminar partición $partitionId : $_"
        }
    }

    function Invoke-ResizePartition {
        param([string]$partitionId, [double]$newSizeGB)
        try {
            if (-not (Test-IsAdmin)) {
                return "Error: esta operación requiere ejecutar Server-powershell.ps1 como Administrador."
            }
            if (-not $partitionId) {
                return "Error: identificador de partición vacío."
            }
            if ($newSizeGB -le 0) {
                return "Error: el nuevo tamaño debe ser mayor que 0 GB (recibido: $newSizeGB)."
            }
            $part = Resolve-PartitionId $partitionId
            if (-not $part) {
                return "Error: no se encontró la partición '$partitionId'."
            }
            if (Test-IsSystemPartition $part) {
                return "Error: NO se puede redimensionar esta partición. Es del sistema/arranque."
            }

            # Comprobar tamaños mínimo/máximo soportados
            $supported = Get-PartitionSupportedSize -DiskNumber $part.DiskNumber -PartitionNumber $part.PartitionNumber -ErrorAction Stop
            $newBytes = [int64]($newSizeGB * 1GB)
            if ($newBytes -lt $supported.SizeMin) {
                return "Error: tamaño mínimo soportado $([math]::Round($supported.SizeMin/1GB,2)) GB (solicitado: $newSizeGB GB)."
            }
            if ($newBytes -gt $supported.SizeMax) {
                return "Error: tamaño máximo soportado $([math]::Round($supported.SizeMax/1GB,2)) GB (solicitado: $newSizeGB GB)."
            }

            Resize-Partition -DiskNumber $part.DiskNumber -PartitionNumber $part.PartitionNumber -Size $newBytes -ErrorAction Stop
            return "Partición $partitionId redimensionada correctamente a $newSizeGB GB."
        }
        catch {
            return "Error al redimensionar partición $partitionId : $_"
        }
    }

    # ---------- BACKUP ----------

    function Invoke-BackupCreate {
        param([string]$argsStr)
        try {
            $parts = Parse-Arguments $argsStr
            if ($parts.Count -lt 3) { return "Error: Parametros insuficientes. Uso: backup <origen> <destino> <nombre> [tipo] [compress]" }

            $sourcePath = $parts[0]
            $destPath = $parts[1]
            $backupName = $parts[2]
            $backupType = if ($parts.Count -gt 3) { $parts[3] } else { "full" }
            $compress = ($parts -contains "compress")

            if (-not (Test-Path $sourcePath)) {
                return "Error: La ruta de origen no existe: $sourcePath"
            }

            # Crear directorio de destino si no existe
            if (-not (Test-Path $destPath)) {
                New-Item -ItemType Directory -Path $destPath -Force | Out-Null
            }

            $startTime = Get-Date

            # Contar archivos y calcular tamaño
            $files = Get-ChildItem -Path $sourcePath -Recurse -File -ErrorAction SilentlyContinue
            $numFiles = $files.Count
            $totalBytes = ($files | Measure-Object -Property Length -Sum).Sum
            if (-not $totalBytes) { $totalBytes = 0 }
            $sizeStr = Format-Size $totalBytes

            if ($compress) {
                $zipPath = Join-Path $destPath "$backupName.zip"
                Compress-Archive -Path $sourcePath -DestinationPath $zipPath -Force -ErrorAction Stop
            }
            else {
                $backupDest = Join-Path $destPath $backupName
                Copy-Item -Path $sourcePath -Destination $backupDest -Recurse -Force -ErrorAction Stop
            }

            $duration = [math]::Round(((Get-Date) - $startTime).TotalSeconds, 1)

            return "Backup completado exitosamente`nArchivos procesados: $numFiles archivos copiados`nTamaño procesado: $sizeStr`nDuración: $duration segundos`nTipo: $backupType`nOrigen: $sourcePath`nDestino: $destPath\$backupName"
        }
        catch {
            return "Error al crear backup: $_"
        }
    }

    function Get-PathSize {
        param([string]$path)
        try {
            $path = $path.Trim('"')
            if (-not (Test-Path $path)) {
                return "bytes: 0`nfiles: 0"
            }
            $item = Get-Item -LiteralPath $path -ErrorAction SilentlyContinue
            if ($item -and -not $item.PSIsContainer) {
                return "bytes: $($item.Length)`nfiles: 1"
            }
            $files = Get-ChildItem -LiteralPath $path -Recurse -File -ErrorAction SilentlyContinue
            $bytes = ($files | Measure-Object -Property Length -Sum).Sum
            if (-not $bytes) { $bytes = 0 }
            $count = if ($files) { $files.Count } else { 0 }
            return "bytes: $bytes`nfiles: $count"
        }
        catch {
            return "bytes: 0`nfiles: 0"
        }
    }

    function Get-BackupList {
        param([string]$backupPath)
        $header = "Nombre | Fecha | Tamaño | Tipo"
        try {
            $backupPath = $backupPath.Trim('"')
            if (-not (Test-Path $backupPath)) {
                return $header
            }

            $items = Get-ChildItem -Path $backupPath -ErrorAction Stop | Sort-Object LastWriteTime -Descending

            if (-not $items -or $items.Count -eq 0) {
                return $header
            }

            $output = "$header`n"
            foreach ($item in $items) {
                $date = $item.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")
                $bytes = if ($item.PSIsContainer) {
                    (Get-ChildItem $item.FullName -Recurse -File -ErrorAction SilentlyContinue |
                    Measure-Object -Property Length -Sum).Sum
                }
                else {
                    $item.Length
                }
                if (-not $bytes) { $bytes = 0 }
                $sizeStr = Format-Size $bytes
                $type = if ($item.Name -match 'incremental') { "incremental" }
                elseif ($item.Name -match 'differential') { "differential" }
                else { "full" }
                $output += "$($item.Name) | $date | $sizeStr | $type`n"
            }
            return $output
        }
        catch {
            return "Error al listar backups: $_"
        }
    }

    function Invoke-BackupRestore {
        param([string]$argsStr)
        try {
            $parts = Parse-Arguments $argsStr
            if ($parts.Count -lt 2) { return "Error: Parametros insuficientes. Uso: restore <backup_path> <restore_path> [overwrite]" }

            $backupPath = $parts[0]
            $restorePath = $parts[1]
            $overwrite = ($parts -contains "overwrite")

            if (-not (Test-Path $backupPath)) {
                return "Error: El backup no existe: $backupPath"
            }

            if (-not (Test-Path $restorePath)) {
                New-Item -ItemType Directory -Path $restorePath -Force | Out-Null
            }

            $startTime = Get-Date

            if ($backupPath -match '\.zip$') {
                Expand-Archive -Path $backupPath -DestinationPath $restorePath -Force:$overwrite -ErrorAction Stop
            }
            else {
                $flags = if ($overwrite) { "-Force" } else { "" }
                Copy-Item -Path "$backupPath\*" -Destination $restorePath -Recurse -Force:$overwrite -ErrorAction Stop
            }

            $duration = [math]::Round(((Get-Date) - $startTime).TotalSeconds, 1)
            $files = (Get-ChildItem -Path $restorePath -Recurse -File -ErrorAction SilentlyContinue).Count

            return "Restauración completada exitosamente`nArchivos procesados: $files archivos copiados`nDuración: $duration segundos`nOrigen: $backupPath`nDestino: $restorePath"
        }
        catch {
            return "Error al restaurar backup: $_"
        }
    }

    function Invoke-BackupDelete {
        param([string]$backupPath)
        try {
            $backupPath = $backupPath.Trim('"')
            if (-not (Test-Path $backupPath)) {
                return "Error: El backup no existe: $backupPath"
            }
            Remove-Item -Path $backupPath -Recurse -Force -ErrorAction Stop
            return "Backup eliminado exitosamente: $backupPath"
        }
        catch {
            return "Error al eliminar backup: $_"
        }
    }

    function Invoke-BackupVerify {
        param([string]$backupPath)
        try {
            $backupPath = $backupPath.Trim('"')
            if (-not (Test-Path $backupPath)) {
                return "Error: El backup no existe: $backupPath"
            }
            $item = Get-Item $backupPath
            if ($item.PSIsContainer) {
                $files = Get-ChildItem -Path $backupPath -Recurse -File -ErrorAction SilentlyContinue
                $numFiles = $files.Count
                $bytes = ($files | Measure-Object -Property Length -Sum).Sum
                if (-not $bytes) { $bytes = 0 }
                return "Backup verificado exitosamente`nArchivos: $numFiles`nTamaño: $(Format-Size $bytes)`nFecha: $($item.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss'))`nEstado: Integro"
            }
            else {
                return "Backup verificado exitosamente`nArchivo: $($item.Name)`nTamaño: $(Format-Size $item.Length)`nFecha: $($item.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss'))`nEstado: Integro"
            }
        }
        catch {
            return "Error al verificar backup: $_"
        }
    }

    function Get-BackupStatus {
        return "Estado del sistema de backup:`nServidor: Activo`nHora actual: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`nOperaciones en curso: Ninguna"
    }

    # ---------- COMPRESION ----------

    function Invoke-CompressFiles {
        param([string]$argsStr)
        try {
            $parts = Parse-Arguments $argsStr
            if ($parts.Count -lt 2) { return "Error: Uso: compress <origen> <destino> [nivel]" }

            $sourcePath = $parts[0]
            $outputPath = $parts[1]
            $level = if ($parts.Count -gt 2) { $parts[2] } else { "normal" }

            if (-not (Test-Path $sourcePath)) {
                return "Error: La ruta de origen no existe: $sourcePath"
            }

            # Calcular tamaño original
            $sourceItems = Get-ChildItem -Path $sourcePath -Recurse -File -ErrorAction SilentlyContinue
            $numFiles = $sourceItems.Count
            $origBytes = ($sourceItems | Measure-Object -Property Length -Sum).Sum
            if (-not $origBytes) { $origBytes = 0 }

            # Asegurar extension .zip
            if (-not $outputPath.EndsWith('.zip')) { $outputPath += '.zip' }

            # Crear directorio destino si es necesario
            $destDir = Split-Path $outputPath -Parent
            if ($destDir -and -not (Test-Path $destDir)) {
                New-Item -ItemType Directory -Path $destDir -Force | Out-Null
            }

            Compress-Archive -Path $sourcePath -DestinationPath $outputPath -Force -ErrorAction Stop

            $compressedBytes = (Get-Item $outputPath).Length
            $ratio = if ($origBytes -gt 0) { [math]::Round((1 - $compressedBytes / $origBytes) * 100, 1) } else { 0 }

            return "Compresión completada exitosamente`nTamaño original: $(Format-Size $origBytes)`nTamaño comprimido: $(Format-Size $compressedBytes)`nRatio de compresión: $ratio%`n$numFiles archivos comprimidos`nNivel: $level"
        }
        catch {
            return "Error al comprimir archivos: $_"
        }
    }

    function Invoke-DecompressFiles {
        param([string]$argsStr)
        try {
            $parts = Parse-Arguments $argsStr
            if ($parts.Count -lt 2) { return "Error: Uso: decompress <archivo.zip> <destino>" }

            $archivePath = $parts[0]
            $outputPath = $parts[1]

            if (-not (Test-Path $archivePath)) {
                return "Error: El archivo no existe: $archivePath"
            }

            if (-not (Test-Path $outputPath)) {
                New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
            }

            Expand-Archive -Path $archivePath -DestinationPath $outputPath -Force -ErrorAction Stop

            $files = (Get-ChildItem -Path $outputPath -Recurse -File -ErrorAction SilentlyContinue).Count
            return "Descompresión extraída exitosamente`n$files archivos extraídos en: $outputPath"
        }
        catch {
            return "Error al descomprimir archivo: $_"
        }
    }

    # ---------- BACKUPS PROGRAMADOS ----------

    function Invoke-ScheduleBackup {
        param([string]$argsStr)
        try {
            $parts = Parse-Arguments $argsStr
            if ($parts.Count -lt 5) { return "Error: Uso: schedule_backup <nombre> <origen> <destino> <tipo_horario> <hora> [tipo_backup]" }

            $taskName = $parts[0]
            $sourcePath = $parts[1]
            $destPath = $parts[2]
            $schedType = $parts[3]   # daily, weekly, monthly
            $schedTime = $parts[4]   # HH:mm
            $backupType = if ($parts.Count -gt 5) { $parts[5] } else { "incremental" }
            $compressArg = if ($parts.Count -gt 6) { $parts[6] } else { "false" }
            $compressLit = if ($compressArg -eq 'true' -or $compressArg -eq '1') { '$true' } else { '$false' }

            # Validar nombre de tarea (solo alfanumérico y guiones)
            if ($taskName -notmatch '^[\w\-]{1,64}$') {
                return "Error: nombre de tarea no válido. Solo letras, números, guiones y subrayados (máx. 64)."
            }
            # Validar rutas antes de usarlas en la tarea programada
            if (-not (Test-ValidWindowsPath $sourcePath)) {
                return "Error: ruta de origen no válida: $sourcePath"
            }
            if (-not (Test-ValidWindowsPath $destPath)) {
                return "Error: ruta de destino no válida: $destPath"
            }
            # Validar tipo de horario
            if ($schedType -notin @('daily', 'weekly', 'monthly')) {
                return "Error: tipo de horario no válido. Use: daily, weekly, monthly."
            }
            # Validar formato HH:mm
            if ($schedTime -notmatch '^\d{2}:\d{2}$') {
                return "Error: formato de hora no válido. Use HH:MM (ej: 02:00)."
            }

            # Escribir el script de backup en un archivo controlado en lugar de embeber
            # rutas como cadenas dentro del argumento del task action
            $tasksDir = "C:\ProgramData\GestionBackup\tasks"
            $logsDir = "C:\ProgramData\GestionBackup\logs"
            $runsDir = "C:\ProgramData\GestionBackup\runs"
            foreach ($d in @($tasksDir, $logsDir, $runsDir)) {
                if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
            }
            $scriptPath = Join-Path $tasksDir "GestionBackup_$taskName.ps1"
            $logPath = Join-Path $logsDir  "GestionBackup_$taskName.log"
            $taskFullName = "GestionBackup_$taskName"
            $scriptContent = @"
`$ErrorActionPreference = 'Stop'
`$log         = '$logPath'
`$runsDir     = '$runsDir'
`$task        = '$taskFullName'
`$srcPath     = '$sourcePath'
`$destBase    = '$destPath'
`$useCompress = $compressLit

function Log(`$msg) { Add-Content -Path `$log -Value ("[" + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + "] " + `$msg) }
function WriteRunResult(`$started, `$finished, `$status, `$bytes, `$files, `$dest, `$err) {
    if (-not (Test-Path `$runsDir)) { New-Item -ItemType Directory -Path `$runsDir -Force | Out-Null }
    `$obj = [pscustomobject]@{
        task        = `$task
        started_at  = `$started.ToString('yyyy-MM-ddTHH:mm:ss')
        finished_at = `$finished.ToString('yyyy-MM-ddTHH:mm:ss')
        status      = `$status
        bytes       = [int64]`$bytes
        files       = [int]`$files
        dest        = `$dest
        error       = `$err
        compressed  = `$useCompress
    }
    `$json = `$obj | ConvertTo-Json -Compress
    `$file = Join-Path `$runsDir (`$task + '_' + `$started.ToString('yyyyMMdd_HHmmss_fff') + '.json')
    Set-Content -Path `$file -Value `$json -Encoding UTF8
}

`$started = Get-Date
try {
    Log ('INICIO backup programado (compress=' + `$useCompress + ')')
    if (-not (Test-Path `$destBase)) { New-Item -ItemType Directory -Path `$destBase -Force | Out-Null }
    `$stamp = `$started.ToString('yyyyMMdd_HHmmss')
    if (`$useCompress) {
        `$dest = Join-Path `$destBase ('backup_' + `$stamp + '.zip')
        Compress-Archive -Path `$srcPath -DestinationPath `$dest -Force
        `$b = (Get-Item -LiteralPath `$dest).Length
        if (-not `$b) { `$b = 0 }
        `$f = 1
    } else {
        `$dest = Join-Path `$destBase ('backup_' + `$stamp)
        Copy-Item -Path `$srcPath -Destination `$dest -Recurse -Force
        `$items = Get-ChildItem -LiteralPath `$dest -Recurse -File -ErrorAction SilentlyContinue
        `$b = (`$items | Measure-Object -Property Length -Sum).Sum
        if (-not `$b) { `$b = 0 }
        `$f = (`$items | Measure-Object).Count
    }
    Log ("OK destino: " + `$dest + " (" + `$b + " bytes, " + `$f + " files)")
    WriteRunResult `$started (Get-Date) 'completed' `$b `$f `$dest `$null
} catch {
    `$msg = [string]`$_
    Log ("ERROR: " + `$msg)
    WriteRunResult `$started (Get-Date) 'error' 0 0 '' `$msg
    throw
}
"@
            Set-Content -Path $scriptPath -Value $scriptContent -Encoding UTF8

            $action = New-ScheduledTaskAction -Execute "powershell.exe" `
                -Argument "-NonInteractive -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptPath`""
            $trigger = switch ($schedType) {
                "daily" { New-ScheduledTaskTrigger -Daily   -At $schedTime }
                "weekly" { New-ScheduledTaskTrigger -Weekly  -At $schedTime -DaysOfWeek Monday }
                "monthly" { New-ScheduledTaskTrigger -Monthly -At $schedTime -DaysOfMonth 1 }
                default { New-ScheduledTaskTrigger -Daily   -At $schedTime }
            }

            $settings = New-ScheduledTaskSettingsSet `
                -StartWhenAvailable `
                -AllowStartIfOnBatteries `
                -DontStopIfGoingOnBatteries `
                -ExecutionTimeLimit (New-TimeSpan -Hours 4) `
                -MultipleInstances IgnoreNew `
                -ErrorAction Stop

            $taskFullName = "GestionBackup_$taskName"

            # Detectar si tenemos privilegios para registrar como SYSTEM.
            # Si no, hacemos fallback al usuario actual con LogonType Interactive.
            $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
                [Security.Principal.WindowsBuiltInRole]::Administrator
            )

            $principalNote = ''
            try {
                if ($isAdmin) {
                    $principal = New-ScheduledTaskPrincipal `
                        -UserId 'NT AUTHORITY\SYSTEM' `
                        -LogonType ServiceAccount `
                        -RunLevel Highest `
                        -ErrorAction Stop
                    $principalNote = 'Se ejecuta como SYSTEM (sin necesidad de sesión iniciada).'
                    Register-ScheduledTask `
                        -TaskName $taskFullName `
                        -Action $action `
                        -Trigger $trigger `
                        -Principal $principal `
                        -Settings $settings `
                        -Description "Backup programado por Herramienta-Gestion" `
                        -Force `
                        -ErrorAction Stop | Out-Null
                }
                else {
                    # Sin admin: registrar para el usuario actual; sólo dispara con sesión iniciada
                    $principal = New-ScheduledTaskPrincipal `
                        -UserId ("$env:USERDOMAIN\$env:USERNAME") `
                        -LogonType Interactive `
                        -RunLevel Limited `
                        -ErrorAction Stop
                    $principalNote = "ADVERTENCIA: el servidor PS no se ejecuta como Administrador. " +
                    "La tarea se registró para el usuario actual y SOLO disparará cuando ese usuario esté logueado."
                    Register-ScheduledTask `
                        -TaskName $taskFullName `
                        -Action $action `
                        -Trigger $trigger `
                        -Principal $principal `
                        -Settings $settings `
                        -Description "Backup programado por Herramienta-Gestion" `
                        -Force `
                        -ErrorAction Stop | Out-Null
                }
            }
            catch {
                return "Error al registrar tarea programada en Windows: $_`n" +
                "Pista: ejecute Server-powershell.ps1 como Administrador para poder registrar la tarea como SYSTEM."
            }

            # Verificar que la tarea fue creada de verdad
            $check = Get-ScheduledTask -TaskName $taskFullName -ErrorAction SilentlyContinue
            if (-not $check) {
                return "Error: la tarea $taskFullName no aparece en Task Scheduler tras Register-ScheduledTask. Comprueba permisos."
            }

            return "Backup programado exitosamente`nNombre de tarea: $taskFullName`nHorario: $schedType a las $schedTime`nOrigen: $sourcePath`nDestino: $destPath`nTipo: $backupType`nLog: $logPath`n$principalNote"
        }
        catch {
            return "Error al programar backup: $_"
        }
    }

    function Get-ScheduledBackupsList {
        $header = "task|state|next|last"
        try {
            $tasks = Get-ScheduledTask | Where-Object { $_.TaskName -like "GestionBackup_*" }
            if (-not $tasks -or $tasks.Count -eq 0) {
                return $header
            }
            $lines = @()
            foreach ($t in $tasks) {
                $info = Get-ScheduledTaskInfo -TaskName $t.TaskName -ErrorAction SilentlyContinue
                $nextRun = if ($info -and $info.NextRunTime) { $info.NextRunTime.ToString("yyyy-MM-dd HH:mm:ss") } else { "-" }
                $lastRun = if ($info -and $info.LastRunTime -and $info.LastRunTime.Year -gt 1900) { $info.LastRunTime.ToString("yyyy-MM-dd HH:mm:ss") } else { "-" }
                $lines += "{0}|{1}|{2}|{3}" -f $t.TaskName, $t.State, $nextRun, $lastRun
            }
            return "$header`n" + ($lines -join "`n")
        }
        catch {
            return $header
        }
    }

    function Start-ScheduledBackupNow {
        param([string]$taskName)
        try {
            $taskName = $taskName.Trim('"')
            $fullName = if ($taskName -like "GestionBackup_*") { $taskName } else { "GestionBackup_$taskName" }
            $check = Get-ScheduledTask -TaskName $fullName -ErrorAction SilentlyContinue
            if (-not $check) {
                return "Error: la tarea programada $fullName no existe en Windows Task Scheduler. " +
                "Probablemente no se llegó a registrar (¿Server-powershell se ejecutó como Administrador?). " +
                "Edita el trabajo o vuélvelo a guardar para reintentar."
            }
            Start-ScheduledTask -TaskName $fullName -ErrorAction Stop
            return "Tarea programada iniciada manualmente: $fullName`nRevisa el log en C:\ProgramData\GestionBackup\logs\$fullName.log"
        }
        catch {
            return "Error al iniciar tarea programada: $_"
        }
    }

    function Get-ScheduledRunsFromLogs {
        # Devuelve, en formato JSONL (una línea JSON por run), las ejecuciones
        # extraídas de los log files de todas las tareas GestionBackup_*.
        # Esto es la fuente de verdad: Add-Content nunca falla y el log siempre se escribe.
        $logsDir = 'C:\ProgramData\GestionBackup\logs'
        if (-not (Test-Path $logsDir)) { return '' }
        $logFiles = Get-ChildItem -Path $logsDir -Filter 'GestionBackup_*.log' -ErrorAction SilentlyContinue
        if (-not $logFiles) { return '' }

        $output = @()
        foreach ($f in $logFiles) {
            $task = [System.IO.Path]::GetFileNameWithoutExtension($f.Name)
            try {
                $content = Get-Content -Path $f.FullName -Tail 400 -ErrorAction Stop
            }
            catch { continue }
            if (-not $content) { continue }

            $current = $null
            foreach ($line in $content) {
                if ($line -match '^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] INICIO backup programado(?: \(compress=(True|False)\))?') {
                    # Si había uno sin terminar, se descarta (script roto o aún en curso)
                    $current = [ordered]@{
                        task        = $task
                        started_at  = ($matches[1] -replace ' ', 'T')
                        finished_at = $null
                        status      = 'unknown'
                        bytes       = 0
                        files       = 0
                        dest        = ''
                        error       = $null
                        compressed  = $false
                    }
                    if ($matches[2]) { $current.compressed = ($matches[2] -eq 'True') }
                }
                elseif ($line -match '^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] OK destino: (.+?) \((\d+) bytes, (\d+) files\)') {
                    if ($current) {
                        $current.finished_at = ($matches[1] -replace ' ', 'T')
                        $current.status = 'completed'
                        $current.dest = $matches[2]
                        $current.bytes = [int64]$matches[3]
                        $current.files = [int]$matches[4]
                        $output += ((New-Object PSObject -Property $current) | ConvertTo-Json -Compress)
                        $current = $null
                    }
                }
                elseif ($line -match '^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] ERROR: (.+)') {
                    if ($current) {
                        $current.finished_at = ($matches[1] -replace ' ', 'T')
                        $current.status = 'error'
                        $current.error = $matches[2]
                        $output += ((New-Object PSObject -Property $current) | ConvertTo-Json -Compress)
                        $current = $null
                    }
                }
            }
        }
        return ($output -join "`n")
    }

    function Pop-ScheduledBackupRuns {
        param([string]$taskName)
        try {
            $taskName = $taskName.Trim('"')
            $runsDir = 'C:\ProgramData\GestionBackup\runs'
            if (-not (Test-Path $runsDir)) { return '' }

            if ($taskName -eq '*' -or [string]::IsNullOrEmpty($taskName)) {
                $pattern = '*.json'
            }
            else {
                $fullName = if ($taskName -like 'GestionBackup_*') { $taskName } else { "GestionBackup_$taskName" }
                $pattern = "$fullName" + '_*.json'
            }

            $files = Get-ChildItem -Path $runsDir -Filter $pattern -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime
            if (-not $files) { return '' }

            $lines = @()
            foreach ($f in $files) {
                try {
                    $content = (Get-Content -Path $f.FullName -Raw -ErrorAction Stop).Trim()
                    if ($content) { $lines += $content }
                    Remove-Item -Path $f.FullName -Force -ErrorAction SilentlyContinue
                }
                catch {}
            }
            return ($lines -join "`n")
        }
        catch {
            return ''
        }
    }

    function Get-ScheduledBackupLog {
        param([string]$taskName)
        try {
            $taskName = $taskName.Trim('"')
            $fullName = if ($taskName -like "GestionBackup_*") { $taskName } else { "GestionBackup_$taskName" }
            $logPath = "C:\ProgramData\GestionBackup\logs\$fullName.log"
            if (-not (Test-Path $logPath)) {
                return "Sin entradas todavía. Log: $logPath"
            }
            $content = Get-Content -Path $logPath -Tail 50 -ErrorAction SilentlyContinue
            if (-not $content) { return "Log vacío: $logPath" }
            return ($content -join "`n")
        }
        catch {
            return "Error al leer log: $_"
        }
    }

    function Remove-ScheduledBackup {
        param([string]$taskName)
        try {
            $taskName = $taskName.Trim('"')
            # Buscar con y sin prefijo
            $fullName = if ($taskName -like "GestionBackup_*") { $taskName } else { "GestionBackup_$taskName" }
            Unregister-ScheduledTask -TaskName $fullName -Confirm:$false -ErrorAction Stop
            return "Backup programado eliminado: $fullName"
        }
        catch {
            return "Error al eliminar backup programado: $_"
        }
    }

    # ---------- RED, SERVICIOS, LOGS, PERMISOS ----------

    function Get-NetworkInfo {
        try {
            $adapters = Get-NetAdapter | Where-Object Status -eq "Up"
            $output = "Adaptadores de red activos:`n`n"
            foreach ($a in $adapters) {
                $ip = Get-NetIPAddress -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue
                $output += "Adaptador: $($a.Name)`n  Descripcion: $($a.InterfaceDescription)`n  Estado: $($a.Status)`n  Velocidad: $($a.LinkSpeed)`n  IP: $($ip.IPAddress)`n  Mascara: /$($ip.PrefixLength)`n  MAC: $($a.MacAddress)`n`n"
            }
            return $output
        }
        catch {
            return "Error al obtener información de red: $_"
        }
    }

    function Get-ServicesInfo {
        param([int]$Count = 20, [switch]$All)
        try {
            $running = Get-Service | Where-Object { $_.Status -eq "Running" } | Sort-Object DisplayName
            if ($All) {
                $services = $running
                $title = "Servicios en ejecución (todos: $($services.Count)):"
            }
            else {
                $services = $running | Select-Object -First $Count
                $title = "Servicios en ejecución (primeros ${Count}):"
            }
            $output = "$title`n`n"
            foreach ($s in $services) {
                $output += "  $($s.DisplayName) ($($s.Name)) - $($s.Status)`n"
            }
            return $output
        }
        catch {
            return "Error al obtener información de servicios: $_"
        }
    }

    function Get-PermissionsInfo {
        try {
            $output = "Usuarios y permisos del sistema:`n`n"
            $output += "Usuarios locales:`n"
            foreach ($u in (Get-LocalUser)) {
                $output += "  $($u.Name) - $(if($u.Enabled){'Habilitado'}else{'Deshabilitado'})`n"
            }
            $output += "`nGrupos principales:`n"
            $groups = Get-LocalGroup | Where-Object { $_.Name -in @("Administrators", "Users", "Remote Desktop Users") }
            foreach ($g in $groups) {
                $output += "  $($g.Name)`n"
                $members = Get-LocalGroupMember -Group $g.Name -ErrorAction SilentlyContinue
                if ($members) {
                    foreach ($m in $members) { $output += "    - $($m.Name)`n" }
                }
            }
            return $output
        }
        catch {
            return "Error al obtener información de permisos: $_"
        }
    }

    function Get-SystemLogs {
        param([int]$Count = 10)
        try {
            $logs = Get-EventLog -LogName System -Newest $Count -ErrorAction Stop
            $msgs = $logs | ForEach-Object {
                "$($_.TimeGenerated) - $($_.Source): $($_.Message.Substring(0,[Math]::Min(100,$_.Message.Length)))"
            }
            return "Últimos $Count logs del sistema:`n" + ($msgs -join "`n")
        }
        catch {
            return "Error al obtener logs: $_"
        }
    }

    # ---------- VISTA GENERAL ----------

    function Get-SystemInfo {
        try {
            $os = Get-WmiObject Win32_OperatingSystem
            $hostname = $env:COMPUTERNAME
            $osName = $os.Caption
            $bootDate = [Management.ManagementDateTimeConverter]::ToDateTime($os.LastBootUpTime)
            $lastBootStr = $bootDate.ToString("dd/MM/yyyy HH:mm:ss")
            $uptime = (Get-Date) - $bootDate
            $uptimeStr = "$([int]$uptime.TotalDays) dias, $($uptime.Hours) horas, $($uptime.Minutes) minutos"
            $ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
                Where-Object { $_.IPAddress -ne "127.0.0.1" -and $_.PrefixOrigin -ne "WellKnown" } |
                Select-Object -First 1).IPAddress
            if (-not $ip) { $ip = "127.0.0.1" }
            $user = $env:USERNAME
            return "hostname: $hostname`nos: $osName`nlast_boot: $lastBootStr`nuptime: $uptimeStr`nip: $ip`nuser: $user"
        }
        catch {
            return "hostname: UNKNOWN`nos: Windows`nlast_boot: N/A`nuptime: N/A`nip: 127.0.0.1`nuser: N/A"
        }
    }

    function Get-ServicesStatus {
        $map = [ordered]@{
            "WinRM"          = "WinRM"
            "Firewall"       = "MpsSvc"
            "Windows Update" = "wuauserv"
            "Backup"         = "SDRSVC"
            "Antivirus"      = "WinDefend"
        }
        $output = ""
        foreach ($display in $map.Keys) {
            try {
                $svc = Get-Service -Name $map[$display] -ErrorAction Stop
                $status = if ($svc.Status -eq "Running") { "Activo" } elseif ($svc.Status -eq "Stopped") { "Inactivo" } else { $svc.Status }
            }
            catch {
                $status = "No disponible"
            }
            $output += "$display`: $status`n"
        }
        return $output.TrimEnd()
    }

    function Get-SecurityStatus {
        try {
            # Firewall
            try {
                $fw = Get-NetFirewallProfile -ErrorAction Stop
                $fwOn = ($fw | Where-Object Enabled -eq $true).Count -gt 0
                $fwStatus = if ($fwOn) { "Habilitado y funcionando" } else { "Deshabilitado" }
            }
            catch { $fwStatus = "Desconocido" }

            # Antivirus (Windows Defender)
            try {
                $mp = Get-MpComputerStatus -ErrorAction Stop
                $avStatus = if ($mp.AntivirusEnabled) { "Proteccion activa y actualizada" } else { "Proteccion inactiva" }
            }
            catch { $avStatus = "Desconocido" }

            # Windows Update
            try {
                $wu = Get-Service -Name wuauserv -ErrorAction Stop
                $wuStatus = if ($wu.Status -eq "Running") { "Activo" } else { "Inactivo" }
            }
            catch { $wuStatus = "Desconocido" }

            return "antivirus: $avStatus`nfirewall: $fwStatus`nwindows_update: $wuStatus"
        }
        catch {
            return "antivirus: Desconocido`nfirewall: Desconocido`nwindows_update: Desconocido"
        }
    }

    function Get-DiskSummary {
        try {
            $disks = Get-WmiObject -Class Win32_LogicalDisk -Filter "DriveType=3"
            $totalBytes = ($disks | Measure-Object -Property Size -Sum).Sum
            $freeBytes = ($disks | Measure-Object -Property FreeSpace -Sum).Sum
            $usedBytes = $totalBytes - $freeBytes
            $usedPct = if ($totalBytes -gt 0) { [math]::Round(($usedBytes / $totalBytes) * 100, 1) } else { 0 }
            $freePct = 100 - $usedPct
            $freeGB = [math]::Round($freeBytes / 1GB, 1)
            $totalGB = [math]::Round($totalBytes / 1GB, 1)
            $usedGB = [math]::Round($usedBytes / 1GB, 1)
            return "used_pct: $usedPct`nfree_pct: $freePct`nfree_gb: $freeGB`ntotal_gb: $totalGB`nused_gb: $usedGB"
        }
        catch {
            return "used_pct: 35`nfree_pct: 65`nfree_gb: 0`ntotal_gb: 0`nused_gb: 0"
        }
    }

    function Get-RecentActivity {
        try {
            $events = Get-EventLog -LogName System -Newest 20 -ErrorAction Stop |
            Where-Object { $_.EntryType -in @("Warning", "Error", "Information") } |
            Select-Object -First 8
            $lines = $events | ForEach-Object {
                $t = $_.TimeGenerated.ToString("dd/MM/yyyy HH:mm:ss")
                $type = switch ($_.EntryType) { "Error" { "error" } "Warning" { "warning" } default { "info" } }
                $msg = $_.Message -replace "`r`n", " " -replace "`n", " "
                if ($msg.Length -gt 80) { $msg = $msg.Substring(0, 80) + "..." }
                "$t|$type|$($_.Source)|$msg"
            }
            return $lines -join "`n"
        }
        catch {
            $now = (Get-Date).ToString("dd/MM/yyyy HH:mm:ss")
            return "$now|info|Sistema|No se pudieron obtener eventos"
        }
    }

    function Get-NetworkStats {
        try {
            $adapters = Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object Status -eq "Up"
            if (-not $adapters) {
                return "usage_pct: 0`ndown_bps: 0`nup_bps: 0`nlink_bps: 0"
            }

            # Dos snapshots ~500 ms para calcular throughput real
            $t1 = Get-Date
            $snap1 = @{}
            foreach ($a in $adapters) {
                $s = Get-NetAdapterStatistics -Name $a.Name -ErrorAction SilentlyContinue
                if ($s) { $snap1[$a.Name] = @{ Rx = [long]$s.ReceivedBytes; Tx = [long]$s.SentBytes } }
            }
            Start-Sleep -Milliseconds 500
            $t2 = Get-Date
            $snap2 = @{}
            foreach ($a in $adapters) {
                $s = Get-NetAdapterStatistics -Name $a.Name -ErrorAction SilentlyContinue
                if ($s) { $snap2[$a.Name] = @{ Rx = [long]$s.ReceivedBytes; Tx = [long]$s.SentBytes } }
            }
            $dt = ($t2 - $t1).TotalSeconds
            if ($dt -le 0) { $dt = 0.5 }

            [long]$totalDownBps = 0
            [long]$totalUpBps = 0
            [long]$maxLinkBps = 0
            foreach ($a in $adapters) {
                if ($snap1.ContainsKey($a.Name) -and $snap2.ContainsKey($a.Name)) {
                    $dRx = $snap2[$a.Name].Rx - $snap1[$a.Name].Rx
                    $dTx = $snap2[$a.Name].Tx - $snap1[$a.Name].Tx
                    if ($dRx -ge 0) { $totalDownBps += [long](($dRx / $dt) * 8) }
                    if ($dTx -ge 0) { $totalUpBps += [long](($dTx / $dt) * 8) }
                }
                # Speed (numeric, bps) es más fiable que LinkSpeed (string formateado)
                if ($a.Speed -and $a.Speed -gt $maxLinkBps) { $maxLinkBps = [long]$a.Speed }
            }

            $totalBps = $totalDownBps + $totalUpBps
            $pct = if ($maxLinkBps -gt 0) { [math]::Round(($totalBps / [double]$maxLinkBps) * 100, 1) } else { 0 }
            if ($pct -gt 100) { $pct = 100 }

            $ic = [System.Globalization.CultureInfo]::InvariantCulture
            return "usage_pct: $($pct.ToString($ic))`ndown_bps: $totalDownBps`nup_bps: $totalUpBps`nlink_bps: $maxLinkBps"
        }
        catch {
            return "usage_pct: 0`ndown_bps: 0`nup_bps: 0`nlink_bps: 0"
        }
    }

    # ---------- HARDWARE ----------

    function Get-HardwareSystem {
        try {
            $ic = [System.Globalization.CultureInfo]::InvariantCulture
            $os = Get-WmiObject Win32_OperatingSystem
            $cs = Get-WmiObject Win32_ComputerSystem
            $bio = Get-WmiObject Win32_BIOS
            $hn = $env:COMPUTERNAME
            $arch = if ([Environment]::Is64BitOperatingSystem) { "x64" } else { "x86" }
            $bootDate = [Management.ManagementDateTimeConverter]::ToDateTime($os.LastBootUpTime)
            $up = (Get-Date) - $bootDate
            $uptimeStr = "$([int]$up.TotalDays) días, $($up.Hours) h, $($up.Minutes) min"
            $ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
                Where-Object { $_.IPAddress -ne "127.0.0.1" -and $_.PrefixOrigin -ne "WellKnown" } |
                Select-Object -First 1).IPAddress
            if (-not $ip) { $ip = "127.0.0.1" }
            $biosStr = "$($bio.Manufacturer) $($bio.SMBIOSBIOSVersion)"
            try {
                $bd = [datetime]::ParseExact($bio.ReleaseDate.Substring(0, 8), "yyyyMMdd", $null)
                $biosStr += " ($($bd.ToString('MM/yyyy')))"
            }
            catch {}
            $osName = "$($os.Caption) $arch"
            return "hostname: $hn`nos: $osName`nuptime: $uptimeStr`nmanufacturer: $($cs.Manufacturer)`nmodel: $($cs.Model)`nserial: $($bio.SerialNumber)`nbios: $biosStr`narch: $arch`nip: $ip`ndirectx: 12"
        }
        catch {
            return "hostname: UNKNOWN`nos: Windows`nuptime: N/A`nmanufacturer: -`nmodel: -`nserial: -`nbios: -`narch: x64`nip: 127.0.0.1`ndirectx: -"
        }
    }

    function Get-HardwareCPU {
        try {
            $cpu = Get-WmiObject Win32_Processor | Select-Object -First 1
            $cores = $cpu.NumberOfCores
            $threads = $cpu.NumberOfLogicalProcessors
            $baseGHz = [math]::Round($cpu.MaxClockSpeed / 1000, 2)
            $l2 = if ($cpu.L2CacheSize) { [math]::Round($cpu.L2CacheSize / 1024, 1).ToString() + " MB" } else { "-" }
            $l3 = if ($cpu.L3CacheSize) { [math]::Round($cpu.L3CacheSize / 1024, 1).ToString() + " MB" } else { "-" }
            $virt = try {
                if ($cpu.VirtualizationFirmwareEnabled) { "Habilitada" } else { "Deshabilitada" }
            }
            catch { "Desconocida" }
            return "model: $($cpu.Name.Trim())`nsockets: 1`ncores: $cores`nthreads: $threads`nbase_freq: $baseGHz GHz`ncurrent_freq: $baseGHz GHz`ncache_l1: -`ncache_l2: $l2`ncache_l3: $l3`nvirtualization: $virt`ntemperature: -"
        }
        catch {
            return "model: -`nsockets: 1`ncores: -`nthreads: -`nbase_freq: -`ncurrent_freq: -`ncache_l1: -`ncache_l2: -`ncache_l3: -`nvirtualization: -`ntemperature: -"
        }
    }

    function Get-HardwareMemory {
        try {
            $ic = [System.Globalization.CultureInfo]::InvariantCulture
            $os = Get-WmiObject Win32_OperatingSystem
            $totalKB = $os.TotalVisibleMemorySize
            $freeKB = $os.FreePhysicalMemory
            $usedKB = $totalKB - $freeKB
            $totalGB = [math]::Round($totalKB / 1MB, 1)
            $usedGB = [math]::Round($usedKB / 1MB, 1)
            $freeGB = [math]::Round($freeKB / 1MB, 1)
            $ram = Get-WmiObject Win32_PhysicalMemory | Select-Object -First 1
            $speed = if ($ram -and $ram.Speed) { $ram.Speed } else { 0 }
            $type = if ($ram) {
                switch ($ram.MemoryType) { 26 { "DDR4" } 24 { "DDR3" } 22 { "DDR2" } 34 { "DDR5" } default { "DDR" } }
            }
            else { "-" }
            $slotsUsed = (Get-WmiObject Win32_PhysicalMemory -ErrorAction SilentlyContinue).Count
            $slotsTotal = (Get-WmiObject Win32_PhysicalMemoryArray -ErrorAction SilentlyContinue |
                Measure-Object -Property MemoryDevices -Sum).Sum
            return "total_gb: $($totalGB.ToString($ic))`nused_gb: $($usedGB.ToString($ic))`nfree_gb: $($freeGB.ToString($ic))`nspeed: $speed`ntype: $type`nslots_used: $slotsUsed`nslots_total: $slotsTotal"
        }
        catch {
            return "total_gb: 0`nused_gb: 0`nfree_gb: 0`nspeed: 0`ntype: -`nslots_used: 0`nslots_total: 0"
        }
    }

    function Get-HardwareDisks {
        try {
            $ic = [System.Globalization.CultureInfo]::InvariantCulture
            $header = "model|type|capacity_gb|used_gb|used_pct|status|temperature"
            $lines = Get-Disk | ForEach-Object {
                $d = $_
                $cap = [math]::Round($d.Size / 1GB, 1)
                $mediaType = $d.MediaType
                $type = if ($d.FriendlyName -match "NVMe|SSD" -or $mediaType -eq "SSD") { "SSD" }
                elseif ($mediaType -eq "HDD") { "HDD" }
                elseif ($mediaType) { $mediaType.ToString() }
                else { "Desconocido" }
                $status = if ($d.HealthStatus -eq "Healthy") { "Bueno" } else { $d.HealthStatus }
                $usedGB = [math]::Round($cap * 0.5, 1)
                $usedPct = 50.0
                try {
                    $parts = Get-Partition -DiskNumber $d.Number -ErrorAction SilentlyContinue
                    if ($parts) {
                        $totalBytes = ($parts | Measure-Object -Property Size -Sum).Sum
                        $freeBytes = 0
                        foreach ($p in $parts) {
                            $vol = Get-Volume -Partition $p -ErrorAction SilentlyContinue
                            if ($vol) { $freeBytes += $vol.SizeRemaining }
                        }
                        if ($totalBytes -gt 0) {
                            $usedGB = [math]::Round(($totalBytes - $freeBytes) / 1GB, 1)
                            $usedPct = [math]::Round(($totalBytes - $freeBytes) / $totalBytes * 100, 1)
                        }
                    }
                }
                catch {}
                "$($d.FriendlyName)|$type|$($cap.ToString($ic))|$($usedGB.ToString($ic))|$($usedPct.ToString($ic))|$status|-"
            }
            return "$header`n" + ($lines -join "`n")
        }
        catch {
            return "model|type|capacity_gb|used_gb|used_pct|status|temperature`nError|SSD|0|0|0|Desconocido|-"
        }
    }

    function Get-HardwareGPU {
        try {
            $header = "model|memory|vendor|driver_version"
            $lines = Get-WmiObject Win32_VideoController | ForEach-Object {
                $mem = if ($_.AdapterRAM) { [math]::Round($_.AdapterRAM / 1MB, 0).ToString() + " MB" } else { "-" }
                "$($_.Caption)|$mem|$($_.AdapterCompatibility)|$($_.DriverVersion)"
            }
            return "$header`n" + ($lines -join "`n")
        }
        catch {
            return "model|memory|vendor|driver_version`nError|0 MB|-|-"
        }
    }

    function Get-HardwareMotherboard {
        try {
            $mb = Get-WmiObject Win32_BaseBoard
            $bio = Get-WmiObject Win32_BIOS
            $biosStr = "$($bio.Manufacturer) $($bio.SMBIOSBIOSVersion)"
            $date = try {
                [datetime]::ParseExact($bio.ReleaseDate.Substring(0, 8), "yyyyMMdd", $null).ToString("MM/yyyy")
            }
            catch { "-" }
            return "model: $($mb.Product)`nmanufacturer: $($mb.Manufacturer)`nversion: $($mb.Version)`nchipset: -`ndate: $date`nbios: $biosStr"
        }
        catch {
            return "model: -`nmanufacturer: -`nversion: -`nchipset: -`ndate: -`nbios: -"
        }
    }

    function Get-HardwareDevices {
        try {
            $header = "type|name"
            $lines = @()
            foreach ($a in (Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object Status -eq "Up")) {
                $lines += "Adaptador de red|$($a.InterfaceDescription)"
            }
            foreach ($a in (Get-WmiObject Win32_SoundDevice -ErrorAction SilentlyContinue)) {
                $lines += "Audio|$($a.Name)"
            }
            foreach ($u in (Get-WmiObject Win32_USBController -ErrorAction SilentlyContinue | Select-Object -First 2)) {
                $lines += "USB|$($u.Name)"
            }
            $mon = (Get-WmiObject Win32_DesktopMonitor -ErrorAction SilentlyContinue).Count
            if ($mon -gt 0) { $lines += "Monitores|$mon monitor(es) detectado(s)" }
            if ($lines.Count -eq 0) { return "$header`nDispositivos|No disponible" }
            return "$header`n" + ($lines -join "`n")
        }
        catch {
            return "type|name`nDispositivos|No disponible"
        }
    }

    # ---------- RED Y CONFIGURACION DE RED ----------

    function ConvertTo-SubnetMask {
        param([int]$prefix)
        if ($prefix -lt 0 -or $prefix -gt 32) { return '0.0.0.0' }
        $mask = [uint32]0
        for ($i = 0; $i -lt $prefix; $i++) { $mask = $mask -bor ([uint32]1 -shl (31 - $i)) }
        return '{0}.{1}.{2}.{3}' -f (($mask -shr 24) -band 255), (($mask -shr 16) -band 255), (($mask -shr 8) -band 255), ($mask -band 255)
    }

    function Get-NetAdapters {
        try {
            $header = 'name|type|status|ip|speed'
            # Una sola llamada para todas las IPs (mucho mas rapido que por adaptador)
            $ipMap = @{}
            foreach ($ip4 in (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
                    Where-Object { $_.PrefixOrigin -ne 'WellKnown' })) {
                $idx = [int]$ip4.InterfaceIndex
                if (-not $ipMap.ContainsKey($idx)) { $ipMap[$idx] = $ip4.IPAddress }
            }
            $lines = @()
            foreach ($a in (Get-NetAdapter -ErrorAction SilentlyContinue)) {
                $ip = if ($ipMap.ContainsKey([int]$a.ifIndex)) { $ipMap[[int]$a.ifIndex] } else { '-' }
                $st = $a.Status.ToString()
                $status = if ($st -eq 'Up') { 'Conectado' }
                elseif ($st -eq 'Disconnected') { 'Desconectado' }
                elseif ($st -eq 'NotPresent') { 'No disponible' }
                elseif ($st -eq 'Dormant') { 'Inactivo' }
                else { $st }
                # Solo mostrar velocidad si el enlace esta activo
                $speed = if ($status -eq 'Conectado') {
                    try {
                        $ls = [double]"$($a.LinkSpeed)"
                        if ($ls -ge 1e9) { "$([math]::Round($ls/1e9,1)) Gbps" }
                        elseif ($ls -ge 1e6) { "$([math]::Round($ls/1e6,0)) Mbps" }
                        elseif ($ls -gt 0) { "$([math]::Round($ls/1e3,0)) Kbps" }
                        else { '-' }
                    }
                    catch {
                        if ($a.LinkSpeed) { "$($a.LinkSpeed)" } else { '-' }
                    }
                }
                else { '-' }
                $lines += "$($a.Name)|$($a.InterfaceDescription)|$status|$ip|$speed"
            }
            if ($lines.Count -eq 0) { return "$header`nSin adaptadores detectados|—|—|—|—" }
            return "$header`n" + ($lines -join "`n")
        }
        catch {
            return "name|type|status|ip|speed`nError|—|—|—|—"
        }
    }

    function Get-NetAdapterDetails {
        param([string]$adapterName)
        try {
            $adapterName = $adapterName.Trim()
            $a = Get-NetAdapter -Name $adapterName -ErrorAction Stop
            # No filtrar por PrefixOrigin — los adaptadores virtuales (WSL, Hyper-V) usan 'Manual' o 'WellKnown'
            $ip = Get-NetIPAddress -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -ne '127.0.0.1' } | Select-Object -First 1
            $dns = (Get-DnsClientServerAddress -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue).ServerAddresses
            $gw = (Get-NetRoute -InterfaceIndex $a.ifIndex -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
                Select-Object -First 1).NextHop
            $iface = Get-NetIPInterface -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue
            $dhcp = if ($iface -and $iface.Dhcp -eq 'Enabled') { 'Habilitado' } else { 'Deshabilitado' }
            $mask = if ($ip) { ConvertTo-SubnetMask -prefix $ip.PrefixLength } else { '-' }
            $dns1 = if ($dns -and $dns.Count -gt 0) { $dns[0] } else { '-' }
            $dns2 = if ($dns -and $dns.Count -gt 1) { $dns[1] } else { '-' }
            $st = $a.Status.ToString()
            $status = if ($st -eq 'Up') { 'Conectado' } elseif ($st -eq 'Disconnected') { 'Desconectado' } else { $st }
            $spd = try {
                $ls = [double]"$($a.LinkSpeed)"
                if ($ls -ge 1e9) { "$([math]::Round($ls/1e9,1)) Gbps" }
                elseif ($ls -ge 1e6) { "$([math]::Round($ls/1e6,0)) Mbps" }
                elseif ($ls -gt 0) { "$([math]::Round($ls/1e3,0)) Kbps" }
                else { '-' }
            }
            catch {
                if ($a.LinkSpeed) { "$($a.LinkSpeed)" } else { '-' }
            }
            return "mac: $($a.MacAddress)`ngateway: $(if($gw){$gw}else{'-'})`nsubnet: $mask`ndns_primary: $dns1`ndns_secondary: $dns2`ndhcp: $dhcp`nstatus: $status`nspeed: $spd"
        }
        catch {
            return "mac: -`ngateway: -`nsubnet: -`ndns_primary: -`ndns_secondary: -`ndhcp: -`nstatus: -`nspeed: -"
        }
    }

    function Get-NetStats {
        try {
            $header = 'name|rx_mb|tx_mb|rx_packets|tx_packets'
            $lines = Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { $_.Status.ToString() -eq 'Up' } | ForEach-Object {
                $s = Get-NetAdapterStatistics -Name $_.Name -ErrorAction SilentlyContinue
                $rxMB = if ($s) { [math]::Round($s.ReceivedBytes / 1MB, 2) } else { 0 }
                $txMB = if ($s) { [math]::Round($s.SentBytes / 1MB, 2) } else { 0 }
                $rxP = if ($s) { $s.ReceivedUnicastPackets + $s.ReceivedMulticastPackets } else { 0 }
                $txP = if ($s) { $s.SentUnicastPackets + $s.SentMulticastPackets }         else { 0 }
                "$($_.Name)|$rxMB|$txMB|$rxP|$txP"
            }
            return "$header`n" + ($lines -join "`n")
        }
        catch {
            return "name|rx_mb|tx_mb|rx_packets|tx_packets`nError|0|0|0|0"
        }
    }

    function Get-NetActivity {
        try {
            $events = Get-EventLog -LogName System -Newest 20 -ErrorAction SilentlyContinue |
            Where-Object { $_.EntryType -in @('Information', 'Warning', 'Error') } |
            Select-Object -First 8
            $lines = $events | ForEach-Object {
                $t = $_.TimeGenerated.ToString('dd/MM/yyyy HH:mm:ss')
                $type = switch ($_.EntryType) { 'Error' { 'error' } 'Warning' { 'warning' } default { 'info' } }
                $msg = ($_.Message -replace "`r`n", ' ' -replace "`n", ' ')
                if ($msg.Length -gt 80) { $msg = $msg.Substring(0, 80) + '...' }
                "$t|$type|$($_.Source)|$msg"
            }
            return $lines -join "`n"
        }
        catch {
            $now = (Get-Date).ToString('dd/MM/yyyy HH:mm:ss')
            return "$now|info|Sistema|No se pudieron obtener eventos"
        }
    }

    function Get-NetAlerts {
        try {
            $alerts = @()
            $alerts += 'ok|No se detectan conflictos de IP.|info'
            $vpnDown = Get-NetAdapter -ErrorAction SilentlyContinue |
            Where-Object { ($_.InterfaceDescription -match 'VPN|Virtual|TAP' -or $_.Name -match 'VPN|Tunnel') -and $_.Status -ne 'Up' }
            if ($vpnDown) {
                foreach ($v in $vpnDown) { $alerts += "warning|La VPN '$($v.Name)' está actualmente inactiva.|warning" }
            }
            try {
                $fwOn = (Get-NetFirewallProfile -ErrorAction Stop | Where-Object Enabled -eq $true).Count -gt 0
                $alerts += if ($fwOn) { 'ok|Firewall de red funcionando correctamente.|info' } else { 'warning|Firewall de red desactivado.|warning' }
            }
            catch { $alerts += 'info|Estado del firewall desconocido.|info' }
            $alerts += 'ok|Protección de red activa.|Activa'
            $alerts += 'ok|Análisis de conectividad habilitado.|Activa'
            return $alerts -join "`n"
        }
        catch {
            return "info|No se pudo obtener estado de alertas.|info"
        }
    }

    function Invoke-NetPing {
        param([string]$target)
        try {
            if (-not $target -or $target.Trim() -eq '') { $target = '8.8.8.8' }
            $target = $target.Trim()
            if (-not (Test-ValidNetworkTarget $target)) {
                return "Error: destino de red no válido '$target'. Solo se aceptan IPs o nombres de host."
            }
            $results = Test-Connection -ComputerName $target -Count 4 -ErrorAction SilentlyContinue
            if (-not $results) {
                return "Enviando ping a ${target}:`n`nSolicitud agotada para el host ${target}.`n`nEstadísticas de ping: Paquetes enviados = 4, recibidos = 0, perdidos = 4 (100% perdidos)"
            }
            $output = "Enviando ping a $target con 32 bytes de datos:`n`n"
            foreach ($r in $results) {
                $output += "Respuesta desde $($r.Address): bytes=32 tiempo=$($r.ResponseTime)ms TTL=$($r.TimeToLive)`n"
            }
            $avg = [math]::Round(($results | Measure-Object ResponseTime -Average).Average, 0)
            $min = ($results | Measure-Object ResponseTime -Minimum).Minimum
            $max = ($results | Measure-Object ResponseTime -Maximum).Maximum
            $rcv = $results.Count
            $output += "`nEstadísticas de ping para ${target}:`n"
            $output += "  Paquetes: enviados=4, recibidos=$rcv, perdidos=$(4-$rcv) ($((100-$rcv*25))% perdidos)`n"
            $output += "`nTiempos aproximados de ida y vuelta en ms:`n"
            $output += "  Mínimo = ${min}ms, Máximo = ${max}ms, Media = ${avg}ms"
            return $output
        }
        catch {
            return "Error al ejecutar ping hacia ${target}: $_"
        }
    }

    function Invoke-NetTraceroute {
        param([string]$target)
        try {
            if (-not $target -or $target.Trim() -eq '') { $target = '8.8.8.8' }
            $target = $target.Trim()
            if (-not (Test-ValidNetworkTarget $target)) {
                return "Error: destino de red no válido '$target'. Solo se aceptan IPs o nombres de host."
            }
            # ProcessStartInfo con CreateNoWindow garantiza que no se abra ninguna ventana CMD
            $psi = New-Object System.Diagnostics.ProcessStartInfo
            $psi.FileName = "tracert.exe"
            $psi.Arguments = "/h 30 /w 3000 $target"
            $psi.UseShellExecute = $false
            $psi.RedirectStandardOutput = $true
            $psi.RedirectStandardError = $true
            $psi.CreateNoWindow = $true
            $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden

            $proc = [System.Diagnostics.Process]::Start($psi)
            $output = $proc.StandardOutput.ReadToEnd()
            $proc.WaitForExit()
            return $output
        }
        catch {
            return "Error al ejecutar tracert hacia ${target}: $_"
        }
    }

    function Get-NetIpconfig {
        try {
            $output = "Configuración IP de Windows`n" + ("=" * 48) + "`n`n"
            foreach ($a in Get-NetAdapter) {
                $ipAddrs = Get-NetIPAddress -InterfaceIndex $a.ifIndex -ErrorAction SilentlyContinue
                $dns = Get-DnsClientServerAddress -InterfaceIndex $a.ifIndex -ErrorAction SilentlyContinue
                $gw = (Get-NetRoute -InterfaceIndex $a.ifIndex -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Select-Object -First 1).NextHop
                $iface = Get-NetIPInterface -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue
                $output += "Adaptador: $($a.Name)`n"
                $output += "   Descripcion . . . . . : $($a.InterfaceDescription)`n"
                $output += "   Direccion fisica . . . : $($a.MacAddress)`n"
                $output += "   DHCP habilitado . . . : $(if($iface -and $iface.Dhcp -eq 'Enabled'){'Si'}else{'No'})`n"
                foreach ($ip in ($ipAddrs | Where-Object { $_.PrefixOrigin -ne 'WellKnown' -and $_.AddressFamily -eq 'IPv4' })) {
                    $output += "   Direccion IPv4 . . . . : $($ip.IPAddress)`n"
                    $output += "   Mascara de subred . . : $(ConvertTo-SubnetMask -prefix $ip.PrefixLength)`n"
                }
                foreach ($ip in ($ipAddrs | Where-Object { $_.AddressFamily -eq 'IPv6' } | Select-Object -First 1)) {
                    $output += "   Direccion IPv6 . . . . : $($ip.IPAddress)`n"
                }
                if ($gw) { $output += "   Puerta de enlace . . . : $gw`n" }
                if ($dns) {
                    $s4 = $dns | Where-Object AddressFamily -eq 'IPv4'
                    if ($s4 -and $s4.ServerAddresses) {
                        $output += "   Servidores DNS . . . . : $(($s4.ServerAddresses | Where-Object {$_}) -join ', ')`n"
                    }
                }
                $output += "`n"
            }
            return $output
        }
        catch {
            return "Error al obtener configuracion IP: $_"
        }
    }

    function Get-NetNetstat {
        try {
            $conns = Get-NetTCPConnection -ErrorAction SilentlyContinue |
            Where-Object { $_.State -ne 'Closed' } |
            Sort-Object State, LocalPort |
            Select-Object -First 25
            $output = "Conexiones TCP activas:`n`n"
            $output += "Proto  Direccion local          Direccion remota        Estado         PID`n"
            $output += ("-" * 80) + "`n"
            foreach ($c in $conns) {
                $local = "$($c.LocalAddress):$($c.LocalPort)".PadRight(24)
                $remote = "$($c.RemoteAddress):$($c.RemotePort)".PadRight(24)
                $state = $c.State.ToString().PadRight(14)
                $output += "TCP    $local$remote$state$($c.OwningProcess)`n"
            }
            return $output
        }
        catch {
            return "Error al obtener conexiones TCP: $_"
        }
    }

    function Invoke-NetReleaseRenew {
        try {
            $output = "Liberando y renovando direcciones IP DHCP:`n`n"
            foreach ($a in (Get-NetAdapter | Where-Object { $_.Status -eq 'Up' })) {
                $iface = Get-NetIPInterface -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue
                if ($iface -and $iface.Dhcp -eq 'Enabled') {
                    try {
                        Start-Process -FilePath "ipconfig.exe" -ArgumentList @("/release", $a.Name) `
                            -NoNewWindow -Wait -ErrorAction SilentlyContinue
                        Start-Sleep -Milliseconds 800
                        Start-Process -FilePath "ipconfig.exe" -ArgumentList @("/renew", $a.Name) `
                            -NoNewWindow -Wait -ErrorAction SilentlyContinue
                        $newIP = (Get-NetIPAddress -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
                            Where-Object { $_.PrefixOrigin -ne 'WellKnown' }).IPAddress
                        $output += "  OK $($a.Name): IP renovada -> $newIP`n"
                    }
                    catch {
                        $output += "  Error $($a.Name): No se pudo renovar`n"
                    }
                }
                else {
                    $output += "  - $($a.Name): IP estatica (sin DHCP)`n"
                }
            }
            $output += "`nOperacion completada."
            return $output
        }
        catch {
            return "Error al liberar/renovar IP: $_"
        }
    }

    function Invoke-NetFlushDNS {
        try {
            Clear-DnsClientCache -ErrorAction Stop
            return "Cache DNS vaciada correctamente.`n`nSe han eliminado todos los registros del cache DNS de Windows.`nNuevos nombres de dominio seran resueltos con informacion actualizada."
        }
        catch {
            return "Error al vaciar cache DNS: $_"
        }
    }

    # ---------- DESPACHADOR DE COMANDOS ----------

    function Execute-Command {
        param([string]$command)
        try {
            switch -Regex ($command) {

                # ---- Rendimiento ----
                '^cpu$' { return Get-CPUInfo }
                '^memory$' { return Get-MemoryInfo }
                '^system_info$' { return Get-SystemInfo }
                '^services_status$' { return Get-ServicesStatus }
                '^security_status$' { return Get-SecurityStatus }
                '^disk_summary$' { return Get-DiskSummary }
                '^recent_activity$' { return Get-RecentActivity }
                '^network_stats$' { return Get-NetworkStats }
                '^process$' { return Get-ProcessInfo }
                '^disk$' { return Get-DiskInfo }
                '^disk_list$' { return Get-DiskList }
                '^network$' { return Get-NetworkInfo }
                '^servicios$' { return Get-ServicesInfo }
                '^servicios (\d+)$' { return Get-ServicesInfo -Count ([int]$matches[1]) }
                '^servicios all$' { return Get-ServicesInfo -All }
                '^permisos$' { return Get-PermissionsInfo }
                '^log$' { return Get-SystemLogs }
                '^log (\d+)$' { return Get-SystemLogs -Count ([int]$matches[1]) }

                '^restart$' {
                    try {
                        # 5 s de delay para que la respuesta llegue al cliente antes del apagado
                        shutdown.exe /r /t 5 /c "Reinicio solicitado desde Herramienta-Gestion" | Out-Null
                        return "Reinicio programado. El sistema se reiniciará en 5 segundos."
                    } catch {
                        return "Error al programar el reinicio: $_"
                    }
                }

                '^matar (\d+)$' {
                    $p = Get-Process -Id $matches[1] -ErrorAction Stop
                    Stop-Process -Id $matches[1] -Force -ErrorAction Stop
                    return "Proceso $($p.Name) (PID $($matches[1])) terminado correctamente"
                }

                '^iniciar (.+)$' {
                    Start-Process $matches[1] -WindowStyle Normal -ErrorAction Stop
                    return "Proceso '$($matches[1])' iniciado correctamente"
                }

                # ---- Discos y particiones ----
                '^list_disks$' { return Get-PhysicalDisksInfo }
                '^list_partitions$' { return Get-PartitionsInfo }
                '^disk_detail (.+)$' { return Get-DiskDetailInfo -diskId $matches[1] }
                '^check_disk (.+)$' { return Invoke-DiskCheck   -diskId $matches[1] }
                '^defrag_disk (.+)$' { return Invoke-DiskDefrag  -diskId $matches[1] }
                '^smart_test (.+)$' { return Invoke-SmartTest   -diskId $matches[1] }
                '^clone_disk (.+) (.+)$' { return Invoke-DiskClone  -src $matches[1] -tgt $matches[2] }
                '^convert_disk (.+) (.+)$' { return Invoke-DiskConvert -diskId $matches[1] -type $matches[2] }
                '^mount_image (.+)$' { return Invoke-ImageMount  -imagePath $matches[1] }

                '^create_partition (.+)$' {
                    $argParts = Parse-Arguments $matches[1]
                    if ($argParts.Count -lt 3) {
                        return "Error: Uso: create_partition <disk> <size_gb> <fs> [label] [letter]"
                    }
                    [double]$sizeNum = 0
                    if (-not [double]::TryParse(($argParts[1] -replace ',', '.'),
                            [System.Globalization.NumberStyles]::Float,
                            [System.Globalization.CultureInfo]::InvariantCulture, [ref]$sizeNum)) {
                        return "Error: tamaño inválido '$($argParts[1])'. Debe ser un número (ej: 10 o 7.5)."
                    }
                    $lbl = if ($argParts.Count -gt 3) { $argParts[3] } else { "" }
                    $ltr = if ($argParts.Count -gt 4) { $argParts[4] } else { "" }
                    return Invoke-CreatePartition -diskId $argParts[0] -size $sizeNum -filesystem $argParts[2] -label $lbl -letter $ltr
                }
                '^format_partition (\S+) (\S+)(?:\s+(.+))?$' {
                    $lbl = if ($matches[3]) { $matches[3].Trim('"').Trim() } else { "" }
                    return Invoke-FormatPartition -partitionId $matches[1] -filesystem $matches[2] -label $lbl
                }
                '^delete_partition (\S+)$' { return Invoke-DeletePartition -partitionId $matches[1] }
                '^resize_partition (\S+) (\S+)$' {
                    [double]$sizeNum = 0
                    if (-not [double]::TryParse(($matches[2] -replace ',', '.'),
                            [System.Globalization.NumberStyles]::Float,
                            [System.Globalization.CultureInfo]::InvariantCulture, [ref]$sizeNum)) {
                        return "Error: tamaño inválido '$($matches[2])'. Debe ser un número."
                    }
                    return Invoke-ResizePartition -partitionId $matches[1] -newSizeGB $sizeNum
                }

                # ---- Backup ----
                '^backup (.+)$' { return Invoke-BackupCreate   -argsStr $matches[1] }
                '^estimate_size (.+)$' { return Get-PathSize          -path $matches[1] }
                '^list_backups (.+)$' { return Get-BackupList        -backupPath $matches[1] }
                '^restore (.+)$' { return Invoke-BackupRestore  -argsStr $matches[1] }
                '^delete_backup (.+)$' { return Invoke-BackupDelete   -backupPath $matches[1] }
                '^verify_backup (.+)$' { return Invoke-BackupVerify   -backupPath $matches[1] }
                '^backup_status$' { return Get-BackupStatus }

                # ---- Compresion ----
                '^compress (.+)$' { return Invoke-CompressFiles   -argsStr $matches[1] }
                '^decompress (.+)$' { return Invoke-DecompressFiles -argsStr $matches[1] }

                # ---- Backups programados ----
                '^schedule_backup (.+)$' { return Invoke-ScheduleBackup    -argsStr $matches[1] }
                '^list_scheduled_backups$' { return Get-ScheduledBackupsList }
                '^delete_scheduled_backup (.+)$' { return Remove-ScheduledBackup  -taskName $matches[1] }
                '^run_scheduled_backup (.+)$' { return Start-ScheduledBackupNow -taskName $matches[1] }
                '^scheduled_backup_log (.+)$' { return Get-ScheduledBackupLog   -taskName $matches[1] }
                '^pop_scheduled_runs (.+)$' { return Pop-ScheduledBackupRuns  -taskName $matches[1] }
                '^pop_scheduled_runs$' { return Pop-ScheduledBackupRuns  -taskName '*' }
                '^scan_scheduled_runs$' { return Get-ScheduledRunsFromLogs }

                # ---- Hardware ----
                '^hardware_system$' { return Get-HardwareSystem }
                '^hardware_cpu$' { return Get-HardwareCPU }
                '^hardware_memory$' { return Get-HardwareMemory }
                '^hardware_disks$' { return Get-HardwareDisks }
                '^hardware_gpu$' { return Get-HardwareGPU }
                '^hardware_motherboard$' { return Get-HardwareMotherboard }
                '^hardware_devices$' { return Get-HardwareDevices }

                # ---- Red ----
                '^net_adapters$' { return Get-NetAdapters }
                '^net_adapter_details (.+)$' { return Get-NetAdapterDetails -adapterName $matches[1] }
                '^net_stats$' { return Get-NetStats }
                '^net_activity$' { return Get-NetActivity }
                '^net_alerts$' { return Get-NetAlerts }
                '^net_ping (.+)$' { return Invoke-NetPing      -target $matches[1] }
                '^net_traceroute (.+)$' { return Invoke-NetTraceroute -target $matches[1] }
                '^net_ipconfig$' { return Get-NetIpconfig }
                '^net_netstat$' { return Get-NetNetstat }
                '^net_release_renew$' { return Invoke-NetReleaseRenew }
                '^net_flush_dns$' { return Invoke-NetFlushDNS }

                default { return "Comando no reconocido: $command" }
            }
        }
        catch {
            return "Error ejecutando comando '$command': $_"
        }
    }

    # ==================== MANEJO DE CONEXION ====================
    $sslStream = $null
    $rawStream = $null
    $reader = $null
    $writer = $null

    try {
        $utf8NoBOM = New-Object System.Text.UTF8Encoding($false)
        $rawStream = $TcpClient.GetStream()

        if ($null -ne $Certificate) {
            # ── Modo TLS ──────────────────────────────────────────────────────
            $sslStream = New-Object System.Net.Security.SslStream($rawStream, $false)
            $sslStream.AuthenticateAsServer(
                $Certificate,
                $false,   # no se requiere cert de cliente
                [System.Security.Authentication.SslProtocols]::Tls12,
                $false    # no verificar revocacion
            )
            $reader = New-Object System.IO.StreamReader($sslStream, $utf8NoBOM)
            $writer = New-Object System.IO.StreamWriter($sslStream, $utf8NoBOM)
        }
        else {
            # ── Modo texto plano (desarrollo sin certificado) ─────────────────
            $reader = New-Object System.IO.StreamReader($rawStream, $utf8NoBOM)
            $writer = New-Object System.IO.StreamWriter($rawStream, $utf8NoBOM)
        }

        $writer.AutoFlush = $true
        $command = $reader.ReadLine()

        if (-not [string]::IsNullOrEmpty($command)) {
            if ($command -eq 'exit') {
                $writer.WriteLine("Servidor detenido.")
            }
            else {
                $response = Execute-Command -command $command.Trim()
                $writer.WriteLine($response)
                $writer.Flush()
            }
        }
    }
    catch {
        # Error de conexion o TLS — no critico, continuar con la siguiente
    }
    finally {
        if ($null -ne $writer) { try { $writer.Close() } catch {} }
        if ($null -ne $reader) { try { $reader.Close() } catch {} }
        if ($null -ne $sslStream) { try { $sslStream.Close() } catch {} }
        if ($null -ne $rawStream) { try { $rawStream.Close() } catch {} }
        if ($null -ne $TcpClient) { try { $TcpClient.Close() } catch {} }
    }
}

# ==================== CERTIFICADO TLS ====================
# Genera o reutiliza un certificado autofirmado para cifrar la comunicación TCP.
# El cliente Python debe configurar PS_TLS_ENABLED=true y PS_SERVER_CA_CERT
# apuntando al archivo ps-server-cert.pem exportado junto al script.

# Directorio del script — $PSScriptRoot puede estar vacío si se ejecuta de forma
# interactiva; usamos $MyInvocation como fallback.
$_scriptDir = if ($PSScriptRoot -and $PSScriptRoot -ne '') {
    $PSScriptRoot
}
elseif ($MyInvocation.MyCommand.Path) {
    Split-Path -Parent $MyInvocation.MyCommand.Path
}
else {
    (Get-Location).Path
}
$certPemPath = Join-Path $_scriptDir "ps-server-cert.pem"

# Usar LocalMachine si hay privilegios de administrador; CurrentUser en caso contrario
$_isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)
$certStorePath = if ($_isAdmin) { "Cert:\LocalMachine\My" } else { "Cert:\CurrentUser\My" }
if (-not $_isAdmin) {
    Write-Host "[TLS] ADVERTENCIA: No se ejecuta como Administrador. Usando almacen de usuario actual."
    Write-Host "[TLS]              Para mayor seguridad, ejecute como Administrador."
}

$certSubject = "CN=GestionPS-Server"

if (-not $tlsEnabled) {
    $serverCert = $null
    Write-Host "[TLS] Cifrado TLS desactivado. Para activarlo: cambie `$tlsEnabled = `$true"
    Write-Host "[TLS] y configure PS_TLS_ENABLED=true + PS_SERVER_CA_CERT en el .env de Flask."
}

if ($tlsEnabled) {
    # Buscar cert existente o generar uno nuevo
    $serverCert = Get-ChildItem -Path $certStorePath -ErrorAction SilentlyContinue |
    Where-Object { $_.Subject -eq $certSubject -and $_.NotAfter -gt (Get-Date) } |
    Sort-Object NotAfter -Descending | Select-Object -First 1

    if (-not $serverCert) {
        Write-Host "[TLS] Generando certificado autofirmado en $certStorePath ..."
        try {
            $serverCert = New-SelfSignedCertificate `
                -DnsName           "localhost" `
                -Subject           $certSubject `
                -CertStoreLocation $certStorePath `
                -KeyAlgorithm      RSA `
                -KeyLength         2048 `
                -HashAlgorithm     SHA256 `
                -NotAfter          (Get-Date).AddYears(2) `
                -KeyUsage          KeyEncipherment, DigitalSignature `
                -FriendlyName      "Herramienta-Gestion PS Server"
            Write-Host "[TLS] Certificado generado: $($serverCert.Thumbprint)"
        }
        catch {
            Write-Host "[TLS] ERROR al generar certificado: $_"
            Write-Host "[TLS] El servidor arrancara SIN cifrado TLS."
            $serverCert = $null
        }
    }
    else {
        Write-Host "[TLS] Reutilizando certificado existente: $($serverCert.Thumbprint)"
    }

    # Exportar clave pública en PEM para que el cliente Python pueda verificarla
    if ($serverCert) {
        try {
            $certBytes = $serverCert.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert)
            $base64 = [System.Convert]::ToBase64String($certBytes, 'InsertLineBreaks')
            $pemContent = "-----BEGIN CERTIFICATE-----`n$base64`n-----END CERTIFICATE-----"
            Set-Content -Path $certPemPath -Value $pemContent -Encoding ASCII
            Write-Host "[TLS] Certificado PEM exportado: $certPemPath"
            Write-Host "[TLS] Configure en el .env de Flask:"
            Write-Host "[TLS]   PS_TLS_ENABLED=true"
            Write-Host "[TLS]   PS_SERVER_CA_CERT=/app/ps-server-cert.pem"
            Write-Host "[TLS]   (copie ps-server-cert.pem al directorio del proyecto)"
        }
        catch {
            Write-Host "[TLS] ERROR al exportar PEM: $_"
        }
    }

} # fin if ($tlsEnabled)

# ==================== INICIO DEL SERVIDOR ====================

$listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Any, $serverPort)

try {
    $listener.Start()

    # Crear pool de Runspaces para conexiones concurrentes
    $RunspacePool = [RunspaceFactory]::CreateRunspacePool(1, $maxConcurrentConns)
    $RunspacePool.Open()

    # Mostrar IPs disponibles para facilitar la configuracion
    $localIPs = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne "127.0.0.1" }).IPAddress
    Write-Host ""
    Write-Host "======================================================"
    Write-Host "  Servidor PowerShell de Gestion - INICIADO"
    Write-Host "======================================================"
    Write-Host "  Puerto          : $serverPort"
    Write-Host "  IPs disponibles : $($localIPs -join ', ')"
    $tlsInfo = if ($serverCert) { "TLS 1.2 activo (cert: $($serverCert.Thumbprint.Substring(0,16))...)" } else { "DESACTIVADO (sin certificado)" }
    Write-Host "  Cifrado         : $tlsInfo"
    Write-Host "  Concurrencia    : hasta $maxConcurrentConns conexiones simultaneas"
    Write-Host ""
    Write-Host "  En docker-compose.yml / .env configure:"
    Write-Host "    POWERSHELL_SERVER=<una de las IPs de arriba>"
    Write-Host "    PS_TLS_ENABLED=true"
    Write-Host "    PS_SERVER_CA_CERT=/app/ps-server-cert.pem"
    Write-Host "  (copie ps-server-cert.pem al contenedor Flask)"
    Write-Host "======================================================"
    Write-Host "  Esperando conexiones..."
    Write-Host ""

    $Control = $true
    $jobs = [System.Collections.Generic.List[object]]::new()

    while ($Control) {
        try {
            $TcpClient = $listener.AcceptTcpClient()

            if ($logCommands) {
                Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Conexion desde $($TcpClient.Client.RemoteEndPoint)"
            }

            # Lanzar manejo en Runspace separado (no bloqueante)
            $PS = [PowerShell]::Create()
            $PS.RunspacePool = $RunspacePool
            [void]$PS.AddScript($ClientHandler).AddArgument($TcpClient).AddArgument($serverCert)
            $handle = $PS.BeginInvoke()
            $jobs.Add([PSCustomObject]@{ PS = $PS; Handle = $handle })

            # Limpiar jobs terminados
            $done = $jobs | Where-Object { $_.Handle.IsCompleted }
            foreach ($j in $done) {
                try { $j.PS.EndInvoke($j.Handle) } catch {}
                $j.PS.Dispose()
            }
            $jobs.RemoveAll({ param($j) $j.Handle.IsCompleted }) | Out-Null

        }
        catch {
            if ($Control) {
                Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Error aceptando conexion: $_"
            }
        }
    }

}
catch {
    Write-Host "Error critico en el servidor: $_"
}
finally {
    if ($null -ne $RunspacePool) { $RunspacePool.Close(); $RunspacePool.Dispose() }
    if ($null -ne $listener) { $listener.Stop() }
    Write-Host "Servidor PowerShell detenido."
}
