# modules/particiones/parsers.py
import re
import logging

logger = logging.getLogger(__name__)

def parse_physical_disks_output(output):
    """
    Parsear la salida del comando list_disks para obtener información de discos físicos
    Solo incluye discos físicos reales, excluyendo medios extraíbles como USB
    """
    disks = []
    
    if not output or "Error" in output:
        logger.error(f"Error en salida de discos físicos: {output}")
        return disks
    
    try:
        # Dividir la salida en bloques de disco
        disk_blocks = output.split("\n\n")
        
        for i, block in enumerate(disk_blocks):
            if not block.strip():
                continue
                
            lines = [line.strip() for line in block.strip().split('\n') if line.strip()]
            
            if not lines:
                continue
            
            # Inicializar datos del disco
            disk_data = {
                "id": f"disk{i}",
                "number": i,
                "name": f"Disco {i}",
                "model": "Modelo Desconocido",
                "size": "0 GB",
                "health": "unknown",
                "status": "Desconocido",
                "interface": "Desconocido",
                "serial": "N/A",
                "usage_percent": 0
            }
            
            # Parsear cada línea del bloque
            for line in lines:
                if line.startswith("Disco "):
                    # Extraer número del disco
                    match = re.search(r'Disco (\d+)', line)
                    if match:
                        disk_num = int(match.group(1))
                        disk_data["id"] = f"disk{disk_num}"
                        disk_data["number"] = disk_num
                        disk_data["name"] = f"Disco {disk_num}"
                
                elif line.startswith("Modelo:"):
                    model = line.replace("Modelo:", "").strip()
                    if model and model != "Modelo Desconocido":
                        disk_data["model"] = model
                        # Filtrar USB/medios extraíbles por el modelo
                        if any(usb_keyword in model.lower() for usb_keyword in ["usb", "removable", "flash", "pen drive", "thumb drive"]):
                            logger.debug(f"Excluyendo dispositivo USB/extraíble: {model}")
                            continue
                        disk_data["name"] = f"Disco {disk_data['number']} - {model}"
                
                elif line.startswith("Tamaño:"):
                    size = line.replace("Tamaño:", "").strip()
                    if size:
                        disk_data["size"] = size
                
                elif line.startswith("Estado:"):
                    status = line.replace("Estado:", "").strip()
                    if status:
                        disk_data["status"] = status
                        # Mapear estado a health
                        status_lower = status.lower()
                        if any(good in status_lower for good in ["bueno", "healthy", "ok", "normal"]):
                            disk_data["health"] = "good"
                        elif any(warning in status_lower for warning in ["advertencia", "warning", "caution"]):
                            disk_data["health"] = "warning"
                        elif any(bad in status_lower for bad in ["malo", "bad", "critical", "failed"]):
                            disk_data["health"] = "critical"
                        else:
                            disk_data["health"] = "unknown"
                
                elif line.startswith("Interfaz:"):
                    interface = line.replace("Interfaz:", "").strip()
                    if interface:
                        disk_data["interface"] = interface
                        # Filtrar interfaces típicas de USB
                        if interface.lower() in ["usb", "usb 2.0", "usb 3.0", "usb 3.1", "usb-c"]:
                            logger.debug(f"Excluyendo dispositivo con interfaz USB: {interface}")
                            continue
                
                elif line.startswith("Número de Serie:"):
                    serial = line.replace("Número de Serie:", "").strip()
                    if serial:
                        disk_data["serial"] = serial
            
            # usage_percent se completa después con datos reales de particiones
            # (ver compute_disk_usage_from_partitions). Aquí lo dejamos en 0.
            disk_data["usage_percent"] = 0
            
            # Solo agregar si parece ser un disco físico real
            # Verificar que tenga un tamaño significativo (mayor a 8GB)
            size_match = re.search(r'(\d+(?:\.\d+)?)\s*(TB|GB)', disk_data["size"])
            if size_match:
                size_num = float(size_match.group(1))
                size_unit = size_match.group(2).upper()
                
                # Convertir a GB para comparación
                size_gb = size_num * 1024 if size_unit == "TB" else size_num
                
                # Solo incluir discos mayores a 8GB (para excluir pequeños USB)
                if size_gb > 8:
                    disks.append(disk_data)
                    logger.debug(f"Agregado disco físico: {disk_data['name']} ({disk_data['size']})")
                else:
                    logger.debug(f"Excluyendo dispositivo pequeño: {disk_data['name']} ({disk_data['size']})")
            else:
                # Si no podemos determinar el tamaño, incluirlo por defecto
                disks.append(disk_data)
                logger.debug(f"Agregado disco (tamaño no determinado): {disk_data['name']}")
    
    except Exception as e:
        logger.error(f"Error parseando discos físicos: {str(e)}")
    
    logger.info(f"Parseados {len(disks)} discos físicos válidos")
    return disks


def compute_disk_usage_from_partitions(disks, partitions_by_disk):
    """Rellena el campo `usage_percent` y `size_total_gb` de cada disco a partir
    de sus particiones reales (en lugar de un valor simulado).

    `partitions_by_disk` viene como {"0": [..], "1": [..]} (keys = número de disco
    como string, sin prefijo "disk").
    """
    for d in disks:
        key = str(d.get("number", ""))
        parts = partitions_by_disk.get(key) or []
        total = sum(float(p.get("size_gb") or 0) for p in parts)
        used  = sum(float(p.get("used_gb") or 0) for p in parts)
        if total > 0:
            d["usage_percent"] = round(used / total * 100, 1)
        else:
            d["usage_percent"] = 0
        d["size_total_gb"] = round(total, 2)
        d["used_total_gb"] = round(used,  2)
        d["free_total_gb"] = round(total - used, 2)
    return disks


def parse_partitions_output(output):
    """
    Parsear la salida del comando list_partitions para obtener información de particiones
    """
    partitions = []
    
    if not output or "Error" in output:
        logger.error(f"Error en salida de particiones: {output}")
        return partitions
    
    try:
        # Dividir la salida en bloques de partición
        partition_blocks = output.split("\n\n")
        
        for block in partition_blocks:
            if not block.strip():
                continue
                
            lines = [line.strip() for line in block.strip().split('\n') if line.strip()]
            
            if not lines:
                continue
            
            # Inicializar datos de la partición
            partition_data = {
                "id": "",
                "disk_id": "",
                "number": 0,
                "letter": "",
                "label": "",
                "filesystem": "",
                "size_gb": 0.0,
                "used_gb": 0.0,
                "free_gb": 0.0,
                "used_percent": 0.0,
                "type": "",
                "status": "free"
            }
            
            # Parsear cada línea del bloque
            for line in lines:
                if line.startswith("Partición:"):
                    # Extraer número de partición y disco
                    match = re.search(r'Partición: (\d+) \(Disco (\d+)\)', line)
                    if match:
                        partition_num = int(match.group(1))
                        disk_num = match.group(2)
                        partition_data["number"] = partition_num
                        partition_data["disk_id"] = disk_num
                        partition_data["id"] = f"{disk_num}-{partition_num}"
                
                elif line.startswith("Letra:"):
                    letter = line.replace("Letra:", "").strip()
                    if letter and letter != "-":
                        partition_data["letter"] = letter.replace(":", "")
                
                elif line.startswith("Etiqueta:"):
                    label = line.replace("Etiqueta:", "").strip()
                    if label and label != "Sin etiqueta":
                        partition_data["label"] = label
                
                elif line.startswith("Sistema de archivos:"):
                    filesystem = line.replace("Sistema de archivos:", "").strip()
                    if filesystem and filesystem != "-":
                        partition_data["filesystem"] = filesystem
                
                elif line.startswith("Tamaño:"):
                    size_str = line.replace("Tamaño:", "").strip()
                    size_match = re.search(r'(\d+(?:\.\d+)?)', size_str)
                    if size_match:
                        partition_data["size_gb"] = float(size_match.group(1))
                
                elif line.startswith("Usado:"):
                    used_str = line.replace("Usado:", "").strip()
                    used_match = re.search(r'(\d+(?:\.\d+)?)%', used_str)
                    if used_match:
                        used_percent = float(used_match.group(1))
                        partition_data["used_percent"] = used_percent
                        # Calcular espacio usado y libre
                        if partition_data["size_gb"] > 0:
                            partition_data["used_gb"] = (partition_data["size_gb"] * used_percent) / 100
                            partition_data["free_gb"] = partition_data["size_gb"] - partition_data["used_gb"]
                
                elif line.startswith("Tipo:"):
                    part_type = line.replace("Tipo:", "").strip()
                    if part_type:
                        partition_data["type"] = part_type.lower()
                        
                        # Mapear tipo a status
                        if part_type.lower() in ["primary", "logical", "extended"]:
                            partition_data["status"] = "active"
                        elif part_type.lower() in ["system", "recovery"]:
                            partition_data["status"] = "system"
                        elif part_type.lower() in ["reserved", "msr"]:
                            partition_data["status"] = "reserved"
                        else:
                            partition_data["status"] = "free"
            
            # Solo agregar si tiene datos válidos
            if partition_data["disk_id"] and partition_data["size_gb"] > 0:
                partitions.append(partition_data)
                logger.debug(f"Agregada partición: {partition_data['id']} ({partition_data['size_gb']} GB)")
    
    except Exception as e:
        logger.error(f"Error parseando particiones: {str(e)}")
    
    logger.info(f"Parseadas {len(partitions)} particiones")
    return partitions

def parse_disk_detail_output(output, disk_id):
    """
    Parsear la salida del comando disk_detail para obtener información detallada de un disco
    """
    disk_details = {
        "id": disk_id,
        "name": f"Disco {disk_id}",
        "model": "Modelo Desconocido",
        "serial": "N/A",
        "interface": "Desconocido",
        "size": "0 GB",
        "partitions": 0,
        "status": "Desconocido",
        "smart_status": "No disponible",
        "health": "unknown",
        "temperature": "N/A",
        "hours": "N/A",
        "cycles": "N/A"
    }
    
    if not output or "Error" in output:
        logger.error(f"Error en salida de detalles del disco {disk_id}: {output}")
        return disk_details
    
    try:
        lines = [line.strip() for line in output.split('\n') if line.strip()]
        
        for line in lines:
            if line.startswith("Disco "):
                # Extraer nombre del disco
                disk_details["name"] = line
            
            elif line.startswith("Modelo:"):
                model = line.replace("Modelo:", "").strip()
                if model:
                    disk_details["model"] = model
            
            elif line.startswith("Serial:"):
                serial = line.replace("Serial:", "").strip()
                if serial:
                    disk_details["serial"] = serial
            
            elif line.startswith("Interfaz:"):
                interface = line.replace("Interfaz:", "").strip()
                if interface:
                    disk_details["interface"] = interface
            
            elif line.startswith("Tamaño:"):
                size = line.replace("Tamaño:", "").strip()
                if size:
                    disk_details["size"] = size
            
            elif line.startswith("Particiones:"):
                partitions_str = line.replace("Particiones:", "").strip()
                try:
                    disk_details["partitions"] = int(partitions_str)
                except ValueError:
                    disk_details["partitions"] = 0
            
            elif line.startswith("Estado:"):
                status = line.replace("Estado:", "").strip()
                if status:
                    disk_details["status"] = status
                    # Mapear estado a health
                    status_lower = status.lower()
                    if any(good in status_lower for good in ["bueno", "healthy", "ok"]):
                        disk_details["health"] = "good"
                    elif any(warning in status_lower for warning in ["advertencia", "warning"]):
                        disk_details["health"] = "warning"
                    elif any(bad in status_lower for bad in ["malo", "bad", "critical"]):
                        disk_details["health"] = "critical"
                    else:
                        disk_details["health"] = "unknown"
            
            elif line.startswith("SMART:"):
                smart = line.replace("SMART:", "").strip()
                if smart:
                    disk_details["smart_status"] = smart
            
            elif line.startswith("Temperatura:"):
                temp = line.replace("Temperatura:", "").strip()
                if temp:
                    disk_details["temperature"] = temp
            
            elif line.startswith("Horas de funcionamiento:"):
                hours = line.replace("Horas de funcionamiento:", "").strip()
                if hours:
                    disk_details["hours"] = hours
    
    except Exception as e:
        logger.error(f"Error parseando detalles del disco {disk_id}: {str(e)}")
    
    logger.debug(f"Parseados detalles del disco {disk_id}")
    return disk_details