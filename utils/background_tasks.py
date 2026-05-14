# utils/background_tasks.py
import time
import logging
import re
from datetime import datetime, timedelta

from .powershell_client import send_command_to_powershell
from modules.rendimiento.parsers import parse_process_output

logger = logging.getLogger(__name__)

# Guardar en DB cada N ciclos (cada 5s × 6 = cada 30s)
_DB_PERSIST_EVERY = 6
_cycle = 0

# Estado del hilo expuesto para /health/background.
# Se actualiza al final de cada ciclo exitoso. Si el hilo se cuelga o muere
# silenciosamente, el timestamp deja de avanzar y el endpoint devuelve 503.
_last_refresh_at: datetime | None = None
_last_refresh_error: str | None = None


def get_background_status(stale_after_seconds: int = 30) -> dict:
    """Devuelve el estado del hilo de refresco de fondo.

    `healthy` es True si hubo al menos un ciclo exitoso y han pasado menos
    de `stale_after_seconds` desde el último (por defecto 30 s, suficiente
    margen sobre el intervalo natural de 5 s).
    """
    if _last_refresh_at is None:
        return {
            'healthy': False,
            'reason':  'el hilo aún no ha completado un ciclo',
            'last_refresh': None,
            'seconds_since': None,
            'last_error': _last_refresh_error,
        }
    delta = (datetime.utcnow() - _last_refresh_at).total_seconds()
    return {
        'healthy': delta < stale_after_seconds and _last_refresh_error is None,
        'last_refresh':  _last_refresh_at.isoformat() + 'Z',
        'seconds_since': round(delta, 1),
        'stale_after':   stale_after_seconds,
        'last_error':    _last_refresh_error,
    }


def parse_cpu_output(text):
    try:
        match = re.search(r'CPU:\s*(\d+(?:\.\d+)?)%', text)
        if match:
            return float(match.group(1))
        match = re.search(r'(\d+(?:\.\d+)?)%', text)
        if match:
            return float(match.group(1))
        return 0.0
    except Exception as e:
        logger.error(f"Error parseando CPU: {e}")
        return 0.0


def parse_memory_output(text):
    try:
        match = re.search(r'memoria:\s*(\d+(?:\.\d+)?)%', text)
        if match:
            return float(match.group(1))
        match = re.search(r'(\d+(?:\.\d+)?)%', text)
        if match:
            return float(match.group(1))
        return 0.0
    except Exception as e:
        logger.error(f"Error parseando memoria: {e}")
        return 0.0


def parse_disk_output(text):
    try:
        logger.debug(f"Parseando salida de disco: {text}")

        match = re.search(r'Usado:\s*(\d+(?:\.\d+)?)%.*Libre:\s*(\d+(?:\.\d+)?)%', text)
        if match:
            used = float(match.group(1))
            free = float(match.group(2))
            return {"used": used, "free": free}

        match = re.search(r'Usado:\s*(\d+(?:\.\d+)?)%', text)
        if match:
            used = float(match.group(1))
            return {"used": used, "free": 100 - used}

        logger.warning(f"No se pudo parsear salida de disco: {text}")
        return {"used": 35.0, "free": 65.0}

    except Exception as e:
        logger.error(f"Error parseando disco: {e}")
        return {"used": 35.0, "free": 65.0}


def _persist_metric(app, cpu, memory, disk):
    """Guarda un snapshot de métricas en la base de datos para la máquina local."""
    try:
        from database import db
        from database.models import Machine, SystemMetric
        from config import Config

        with app.app_context():
            machine = Machine.query.filter_by(
                ip=Config.POWERSHELL_SERVER,
                port=Config.POWERSHELL_PORT
            ).first()
            if not machine:
                return

            # Actualizar estado de la máquina
            machine.status = 'online'
            machine.last_seen = datetime.utcnow()

            metric = SystemMetric(
                machine_id=machine.id,
                timestamp=datetime.utcnow(),
                cpu=cpu,
                memory=memory,
                disk_used=disk.get('used'),
                disk_free=disk.get('free'),
            )
            db.session.add(metric)

            # Limpiar métricas antiguas (retención configurable)
            cutoff = datetime.utcnow() - timedelta(days=Config.METRICS_RETENTION_DAYS)
            SystemMetric.query.filter(
                SystemMetric.machine_id == machine.id,
                SystemMetric.timestamp < cutoff
            ).delete()

            db.session.commit()
            logger.debug(f"Métrica persistida en DB (cpu={cpu}, mem={memory})")

    except Exception as e:
        logger.error(f"Error persistiendo métricas en DB: {e}")


def _persist_metrics_remote(app):
    """Muestrea TODAS las máquinas remotas registradas en BD (no la local) y
    persiste un SystemMetric por cada una. Las máquinas inalcanzables se
    saltan (no se crea fila para no contaminar el historial con ceros).

    Los sondeos se hacen en paralelo (hasta 5 a la vez) para que el coste
    total no escale linealmente con el número de máquinas registradas.
    """
    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from database import db
        from database.models import Machine, SystemMetric
        from utils.powershell_client import send_command_to_machine
        from config import Config

        with app.app_context():
            machines = Machine.query.filter(
                ~((Machine.ip == Config.POWERSHELL_SERVER) &
                  (Machine.port == Config.POWERSHELL_PORT))
            ).all()
            if not machines:
                return

            def _sample(m):
                try:
                    cpu_raw = send_command_to_machine('cpu', m.ip, m.port)
                    low = (cpu_raw or '').lower()
                    if ('no se pudo conectar' in low or
                        'error conectando' in low):
                        return None
                    mem_raw  = send_command_to_machine('memory', m.ip, m.port)
                    disk_raw = send_command_to_machine('disk',   m.ip, m.port)
                    return {
                        'id':     m.id,
                        'cpu':    parse_cpu_output(cpu_raw),
                        'memory': parse_memory_output(mem_raw),
                        'disk':   parse_disk_output(disk_raw),
                    }
                except Exception:
                    return None

            results = []
            with ThreadPoolExecutor(max_workers=min(5, len(machines))) as pool:
                futures = [pool.submit(_sample, m) for m in machines]
                for f in as_completed(futures, timeout=20):
                    try:
                        r = f.result()
                    except Exception:
                        r = None
                    if r:
                        results.append(r)

            if not results:
                return

            now = datetime.utcnow()
            for r in results:
                db.session.add(SystemMetric(
                    machine_id=r['id'],
                    timestamp=now,
                    cpu=r['cpu'],
                    memory=r['memory'],
                    disk_used=r['disk'].get('used'),
                    disk_free=r['disk'].get('free'),
                ))
            db.session.commit()
            logger.debug(f"Persistidas {len(results)} métricas remotas")

    except Exception as e:
        logger.error(f"Error persistiendo métricas remotas: {e}")


def background_data_refresh(cache_manager, app=None):
    """Refresca los datos del sistema en segundo plano y los persiste en DB."""
    global _cycle, _last_refresh_at, _last_refresh_error
    logger.info("Iniciando hilo de actualización de datos en segundo plano")

    while True:
        try:
            # Actualizar CPU
            if not cache_manager.is_cache_valid("cpu"):
                cpu_output = send_command_to_powershell('cpu')
                cpu_value = parse_cpu_output(cpu_output)
                cache_manager.update_cache("cpu", cpu_value)
                logger.debug(f"CPU actualizado: {cpu_value}%")

            # Actualizar memoria
            if not cache_manager.is_cache_valid("memory"):
                memory_output = send_command_to_powershell('memory')
                memory_value = parse_memory_output(memory_output)
                cache_manager.update_cache("memory", memory_value)
                logger.debug(f"Memoria actualizada: {memory_value}%")

            # Actualizar disco
            if not cache_manager.is_cache_valid("disk"):
                disk_output = send_command_to_powershell('disk')
                disk_value = parse_disk_output(disk_output)
                cache_manager.update_cache("disk", disk_value)
                logger.debug(f"Disco actualizado: {disk_value}")

            # Actualizar procesos (slow command — refresh every 2 cycles / ~10 s)
            if _cycle % 2 == 0 and not cache_manager.is_cache_valid("processes"):
                proc_output = send_command_to_powershell('process')
                proc_value  = parse_process_output(proc_output)
                if proc_value:
                    cache_manager.update_cache("processes", proc_value)
                    logger.debug(f"Procesos actualizados: {len(proc_value)} entradas")

            # Persistir en DB cada _DB_PERSIST_EVERY ciclos
            _cycle += 1
            if app is not None and _cycle >= _DB_PERSIST_EVERY:
                _cycle = 0
                system_data = cache_manager.get_all_system_data()
                _persist_metric(
                    app,
                    cpu=system_data['cpu']['value'],
                    memory=system_data['memory']['value'],
                    disk=system_data['disk'],
                )
                # También muestrea máquinas remotas para que sus gráficos no
                # arranquen vacíos en /rendimiento o /vista_general
                _persist_metrics_remote(app)

            # Marca de salud para /health/background.
            _last_refresh_at = datetime.utcnow()
            _last_refresh_error = None
            time.sleep(5)

        except Exception as e:
            _last_refresh_error = f"{type(e).__name__}: {e}"
            logger.error(f"Error en actualización de datos en segundo plano: {str(e)}")
            time.sleep(10)
