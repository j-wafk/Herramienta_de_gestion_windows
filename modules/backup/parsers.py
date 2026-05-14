# modules/backup/parsers.py
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def parse_backup_output(text):
    """Parsea la salida del comando de backup de PowerShell"""
    try:
        logger.debug(f"Parseando salida de backup: {text[:100]}...")
        
        result = {
            "success": False,
            "files_processed": 0,
            "size_processed": "0 MB",
            "duration": "0 segundos",
            "error": None
        }
        
        # Verificar si el backup fue exitoso
        if any(keyword in text.lower() for keyword in [
            'completado', 'completada', 'exitoso', 'exitosa', 'success', 'completed'
        ]):
            result["success"] = True
        
        # Extraer número de archivos procesados
        files_match = re.search(r'(\d+)\s+archivos?\s+(procesados?|copiados?)', text, re.IGNORECASE)
        if files_match:
            result["files_processed"] = int(files_match.group(1))
        
        # Extraer tamaño procesado
        size_match = re.search(r'(\d+(?:\.\d+)?)\s*(MB|GB|KB)', text, re.IGNORECASE)
        if size_match:
            result["size_processed"] = f"{size_match.group(1)} {size_match.group(2).upper()}"
        
        # Extraer duración
        duration_match = re.search(r'(\d+(?:\.\d+)?)\s*(segundos?|minutos?|horas?)', text, re.IGNORECASE)
        if duration_match:
            result["duration"] = f"{duration_match.group(1)} {duration_match.group(2)}"
        
        # Verificar errores
        if any(keyword in text.lower() for keyword in ['error', 'fallo', 'failed', 'falló']):
            result["success"] = False
            error_match = re.search(r'(error|fallo|failed):\s*(.+)', text, re.IGNORECASE)
            if error_match:
                result["error"] = error_match.group(2).strip()
        
        return result
        
    except Exception as e:
        logger.error(f"Error al parsear la salida de backup: {str(e)}")
        return {"success": False, "error": str(e)}

def parse_backup_list_output(text):
    """Parsea la salida del comando de lista de backups de PowerShell.

    Formatos tolerados:
      - Cabecera "Nombre | Fecha | Tamaño | Tipo" + N filas
      - Solo cabecera (carpeta vacía)
      - Mensaje "Sin backups..." (ruta inexistente o vacía)
      - Línea separadora "--------"
    """
    try:
        if not text:
            return []
        logger.debug(f"Parseando lista de backups: {text[:100]}...")
        lines = text.strip().splitlines()
        backups = []

        # Mensaje "Sin backups..." → lista vacía
        if any('sin backups' in l.lower() for l in lines[:2]):
            return []

        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Saltar separadores y cabecera
            if line.startswith('-') or set(line) <= {'-', ' '}:
                continue
            if line.lower().startswith('nombre') or line.lower().startswith('error'):
                continue

            parts = [p.strip() for p in line.split('|', 3)]
            if len(parts) < 3:
                continue

            name = parts[0]
            date = parts[1] if len(parts) > 1 else 'Desconocida'
            size = parts[2] if len(parts) > 2 else '0 MB'
            btype = parts[3] if len(parts) > 3 else 'full'

            try:
                ts = datetime.strptime(date, "%Y-%m-%d %H:%M:%S").timestamp()
            except Exception:
                ts = 0

            backups.append({
                "name": name,
                "date": date,
                "size": size,
                "type": btype,
                "status": "completed",
                "timestamp": ts,
            })

        backups.sort(key=lambda x: x["timestamp"], reverse=True)
        return backups

    except Exception as e:
        logger.error(f"Error al parsear la lista de backups: {str(e)}")
        return []


def parse_size_output(text):
    """Parsea la salida de `estimate_size` / `dir_size`: 'bytes: N\\nfiles: N'."""
    out = {"bytes": 0, "files": 0}
    if not text:
        return out
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith('bytes:'):
            try:
                out['bytes'] = int(line.split(':', 1)[1].strip())
            except Exception:
                pass
        elif line.lower().startswith('files:'):
            try:
                out['files'] = int(line.split(':', 1)[1].strip())
            except Exception:
                pass
    return out


def parse_scheduled_tasks_output(text):
    """Parsea la salida tabular de list_scheduled_backups.

    Formato esperado:
        task|state|next|last
        GestionBackup_x|Ready|2026-05-09 02:00:00|2026-05-08 02:00:00
    Tolera el formato antiguo en bloques 'Tarea: ...\\nEstado: ...' como fallback.
    """
    if not text:
        return []
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return []

    # Formato tabular nuevo
    if '|' in lines[0] and lines[0].lower().startswith('task'):
        result = []
        for line in lines[1:]:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) < 4:
                continue
            result.append({
                'task_name': parts[0],
                'state':     parts[1],
                'next_run':  parts[2] if parts[2] != '-' else None,
                'last_run':  parts[3] if parts[3] != '-' else None,
            })
        return result

    # Formato antiguo en bloques
    result = []
    cur = {}
    for line in lines:
        if ':' not in line:
            continue
        k, v = line.split(':', 1)
        k = k.strip().lower()
        v = v.strip()
        if k.startswith('tarea'):
            if cur:
                result.append(cur)
            cur = {'task_name': v, 'state': '', 'next_run': None, 'last_run': None}
        elif k.startswith('estado'):
            cur['state'] = v
        elif k.startswith('proxima') or k.startswith('próxima'):
            cur['next_run'] = v if v.lower() != 'desconocido' else None
        elif k.startswith('ultima') or k.startswith('última'):
            cur['last_run'] = v if v.lower() != 'nunca' else None
    if cur:
        result.append(cur)
    return result

def parse_compression_output(text):
    """Parsea la salida del comando de compresión de PowerShell"""
    try:
        logger.debug(f"Parseando salida de compresión: {text[:100]}...")
        
        result = {
            "success": False,
            "original_size": "0 MB",
            "compressed_size": "0 MB",
            "compression_ratio": "0%",
            "files_compressed": 0,
            "error": None
        }
        
        # Verificar si la compresión fue exitosa
        if any(keyword in text.lower() for keyword in [
            'completado', 'completada', 'exitoso', 'exitosa', 'success', 'compressed'
        ]):
            result["success"] = True
        
        # Extraer tamaño original
        original_match = re.search(r'tamaño original:\s*(\d+(?:\.\d+)?)\s*(MB|GB|KB)', text, re.IGNORECASE)
        if original_match:
            result["original_size"] = f"{original_match.group(1)} {original_match.group(2).upper()}"
        
        # Extraer tamaño comprimido
        compressed_match = re.search(r'tamaño comprimido:\s*(\d+(?:\.\d+)?)\s*(MB|GB|KB)', text, re.IGNORECASE)
        if compressed_match:
            result["compressed_size"] = f"{compressed_match.group(1)} {compressed_match.group(2).upper()}"
        
        # Extraer ratio de compresión
        ratio_match = re.search(r'compresión:\s*(\d+(?:\.\d+)?)%', text, re.IGNORECASE)
        if ratio_match:
            result["compression_ratio"] = f"{ratio_match.group(1)}%"
        
        # Extraer número de archivos comprimidos
        files_match = re.search(r'(\d+)\s+archivos?\s+comprimidos?', text, re.IGNORECASE)
        if files_match:
            result["files_compressed"] = int(files_match.group(1))
        
        # Verificar errores
        if any(keyword in text.lower() for keyword in ['error', 'fallo', 'failed', 'falló']):
            result["success"] = False
            error_match = re.search(r'(error|fallo|failed):\s*(.+)', text, re.IGNORECASE)
            if error_match:
                result["error"] = error_match.group(2).strip()
        
        return result
        
    except Exception as e:
        logger.error(f"Error al parsear la salida de compresión: {str(e)}")
        return {"success": False, "error": str(e)}