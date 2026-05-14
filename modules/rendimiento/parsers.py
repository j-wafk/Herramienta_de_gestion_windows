# modules/rendimiento/parsers.py
import re
import logging

logger = logging.getLogger(__name__)

def parse_cpu_output(text):
    """Parsea la salida del comando de CPU de PowerShell"""
    try:
        logger.debug(f"Parseando salida de CPU: {text}")
        # Buscar un número en el texto
        match = re.search(r'CPU:\s*(\d+(\.\d+)?)%', text)
        if match:
            return float(match.group(1))
        
        # Intentar otro patrón si el anterior falla
        match = re.search(r'(\d+(\.\d+)?)%', text)
        if match:
            return float(match.group(1))
            
        logger.warning(f"No se pudo extraer valor de CPU del texto: {text}")
        return 0.0
    except Exception as e:
        logger.error(f"Error al parsear la salida de CPU: {str(e)}")
        return 0.0

def parse_memory_output(text):
    """Parsea la salida del comando de memoria de PowerShell"""
    try:
        logger.debug(f"Parseando salida de memoria: {text}")
        # Buscar un número en el texto
        match = re.search(r'memoria:\s*(\d+(\.\d+)?)%', text) 
        if match:
            return float(match.group(1))
            
        # Intentar otro patrón si el anterior falla
        match = re.search(r'(\d+(\.\d+)?)%', text)
        if match:
            return float(match.group(1))
        
        logger.warning(f"No se pudo extraer valor de memoria del texto: {text}")    
        return 0.0
    except Exception as e:
        logger.error(f"Error al parsear la salida de memoria: {str(e)}")
        return 0.0

def parse_disk_output(text):
    """Parsea la salida del comando de disco de PowerShell.

    Acepta dos formatos:
    - "Disco usado: 45.5%, Disco libre: 54.5%"  (compatibilidad legacy)
    - "Usado: 45.5% ... Libre: 54.5%"            (formato background_tasks)
    """
    try:
        for pattern in (
            r'Disco\s+usado:\s*(\d+(?:\.\d+)?)%.*?Disco\s+libre:\s*(\d+(?:\.\d+)?)%',
            r'Usado:\s*(\d+(?:\.\d+)?)%.*?Libre:\s*(\d+(?:\.\d+)?)%',
        ):
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                used = float(m.group(1))
                free = float(m.group(2))
                return {'used': used, 'free': free}
        for pattern in (
            r'Disco\s+usado:\s*(\d+(?:\.\d+)?)%',
            r'Usado:\s*(\d+(?:\.\d+)?)%',
        ):
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                used = float(m.group(1))
                return {'used': used, 'free': round(100 - used, 2)}
        logger.warning(f"No se pudo parsear salida de disco: {text}")
        return {'used': 0.0, 'free': 100.0}
    except Exception as e:
        logger.error(f"Error parseando disco: {e}")
        return {'used': 0.0, 'free': 100.0}


def parse_process_output(text):
    """Parsea la salida del comando de procesos de PowerShell.
    Soporta formato pipe-delimitado (Name|Id|CPU|Memory) y formato antiguo de ancho fijo.
    """
    try:
        logger.debug(f"Parseando salida de procesos: {text[:100]}...")
        lines = text.strip().split('\n')
        if not lines:
            return []

        header = lines[0].strip()
        if '|' in header:
            return _parse_pipe_format(lines)
        return _parse_regex_format(lines)

    except Exception as e:
        logger.error(f"Error al parsear la salida de procesos: {str(e)}")
        return []


def _parse_pipe_format(lines):
    """Formato nuevo: Name|Id|CPU|Memory"""
    processes = []
    for i, line in enumerate(lines):
        line = line.strip()
        if i == 0 or not line or '|' not in line:
            continue
        parts = line.split('|')
        if len(parts) < 3:
            continue
        try:
            name    = parts[0].strip()
            pid     = parts[1].strip()
            cpu_str = parts[2].strip().replace(',', '.')
            memory  = parts[3].strip() if len(parts) > 3 else 'N/A'
            if not name or not pid:
                continue
            try:
                cpu_value = float(cpu_str)
            except ValueError:
                cpu_value = 0.0
            processes.append({"name": name, "pid": pid,
                               "cpu": round(cpu_value, 2), "memory": memory})
        except Exception as e:
            logger.warning(f"Error al parsear línea pipe: {line}. Error: {str(e)}")
    processes.sort(key=lambda x: x["cpu"], reverse=True)
    return processes


def _parse_regex_format(lines):
    """Formato antiguo: columnas de ancho fijo con posible desalineamiento.
    Usa regex para extraer campos independientemente del padding del nombre.
    """
    import re
    processes = []
    # Patrón: nombre (texto hasta los últimos espacios) + PID (dígitos) + CPU (número) + memoria
    pattern = re.compile(
        r'^(.+?)\s+(\d+)\s+([\d,\.]+)\s+(.+)$'
    )
    for i, line in enumerate(lines):
        line = line.strip()
        if i == 0 or not line:
            continue
        # Saltar líneas de separador o encabezado
        if 'Name' in line and ('Id' in line or 'CPU' in line):
            continue
        m = pattern.match(line)
        if not m:
            continue
        try:
            name    = m.group(1).strip()
            pid     = m.group(2).strip()
            cpu_str = m.group(3).strip().replace(',', '.')
            memory  = m.group(4).strip()
            try:
                cpu_value = float(cpu_str)
            except ValueError:
                cpu_value = 0.0
            processes.append({"name": name, "pid": pid,
                               "cpu": round(cpu_value, 2), "memory": memory})
        except Exception as e:
            logger.warning(f"Error al parsear línea regex: {line}. Error: {str(e)}")
    processes.sort(key=lambda x: x["cpu"], reverse=True)
    return processes