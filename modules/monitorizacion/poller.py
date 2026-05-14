# modules/monitorizacion/poller.py
"""
Poller en segundo plano que comprueba periódicamente cada servicio
monitorizado abriendo un socket TCP / enviando paquete UDP a IP:puerto.

Actualiza last_status, last_check, last_latency_ms y guarda un ServiceCheck
SOLO cuando el estado cambia (para no inflar la tabla).
"""
import logging
import socket
import threading
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Configuración por defecto
POLL_INTERVAL_SEC = 30   # cada 30 s recorre todos los servicios
SOCKET_TIMEOUT    = 3.0  # segundos por check
MAX_CHECKS_PER_SVC = 200  # poda


def _check_tcp(ip, port, timeout=SOCKET_TIMEOUT):
    """Devuelve (status, latency_ms, message). Status: up|down|warning."""
    t0 = time.monotonic()
    try:
        with socket.create_connection((ip, int(port)), timeout=timeout):
            ms = (time.monotonic() - t0) * 1000.0
            if ms > 1000:
                return 'warning', ms, f'Latencia alta ({int(ms)} ms)'
            return 'up', ms, f'Respondió en {int(ms)} ms'
    except (socket.timeout, TimeoutError):
        return 'down', None, f'Timeout tras {timeout}s'
    except (ConnectionRefusedError, OSError) as e:
        return 'down', None, f'{type(e).__name__}: {e}'
    except Exception as e:
        return 'down', None, f'Error inesperado: {e}'


def _check_udp(ip, port, timeout=SOCKET_TIMEOUT):
    """Para UDP no hay handshake; intentamos enviar un datagram y leer.
    Si conseguimos enviar y no hay error inmediato, asumimos 'up' con un mensaje
    que aclara la limitación del protocolo.
    """
    t0 = time.monotonic()
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        s.sendto(b'\x00', (ip, int(port)))
        # Intentar leer respuesta — si la hay, mejor confianza.
        try:
            s.recvfrom(1024)
            ms = (time.monotonic() - t0) * 1000.0
            return 'up', ms, f'Respondió a UDP en {int(ms)} ms'
        except socket.timeout:
            ms = (time.monotonic() - t0) * 1000.0
            # No respuesta no implica caído en UDP; lo dejamos como warning
            # informativo. Si quieres tratarlo como up, cambia a 'up'.
            return 'warning', ms, 'UDP enviado, sin respuesta (normal en muchos servicios UDP)'
    except (ConnectionRefusedError, OSError) as e:
        return 'down', None, f'{type(e).__name__}: {e}'
    except Exception as e:
        return 'down', None, f'Error inesperado: {e}'
    finally:
        if s:
            try: s.close()
            except Exception: pass


def check_service(service):
    """Realiza UN check sobre un MonitoredService y devuelve (status, latency, msg)."""
    if (service.protocol or 'TCP').upper() == 'UDP':
        return _check_udp(service.ip, service.port)
    return _check_tcp(service.ip, service.port)


def _prune_checks(db, ServiceCheck, service_id, keep=MAX_CHECKS_PER_SVC):
    """Mantiene a lo sumo `keep` ServiceCheck por servicio."""
    total = ServiceCheck.query.filter_by(service_id=service_id).count()
    if total <= keep:
        return
    keep_ids = [c.id for c in (ServiceCheck.query
                .filter_by(service_id=service_id)
                .order_by(ServiceCheck.timestamp.desc())
                .limit(keep)
                .all())]
    if keep_ids:
        ServiceCheck.query.filter(
            ServiceCheck.service_id == service_id,
            ~ServiceCheck.id.in_(keep_ids),
        ).delete(synchronize_session=False)


def run_poll_cycle(app):
    """Ejecuta UN ciclo completo de checks para todos los servicios habilitados."""
    from database import db
    from database.models import MonitoredService, ServiceCheck, Machine
    # Acumulador de eventos para disparar notificaciones DESPUÉS del commit
    # (así nunca pierdes el cambio si el render del email falla)
    service_down_events = []   # tuplas (svc, prev_status, machine_name)
    machine_offline_events = []  # tuplas (machine,)

    with app.app_context():
        services = MonitoredService.query.filter_by(enabled=True).all()
        # Pre-cargar máquinas para resolver machine_name en eventos
        machines_by_id = {m.id: m for m in Machine.query.all()}
        # Estados previos de máquinas para detectar online→offline
        prev_machine_status = {m.id: m.status for m in machines_by_id.values()}

        now = datetime.utcnow()
        for svc in services:
            try:
                status, latency, msg = check_service(svc)
            except Exception as e:
                status, latency, msg = 'down', None, f'Excepción durante check: {e}'

            prev_status = svc.last_status
            svc.last_status     = status
            svc.last_check      = now
            svc.last_latency_ms = latency
            svc.last_message    = msg

            # Crear ServiceCheck solo si cambia el estado
            if prev_status != status:
                evt = ServiceCheck(
                    service_id = svc.id,
                    timestamp  = now,
                    status     = status,
                    message    = msg,
                    latency_ms = latency,
                )
                db.session.add(evt)
                logger.info(f"[monit] {svc.name} {svc.ip}:{svc.port} {prev_status}→{status}")

                # Encolamos notificación: servicio bajó a 'down' desde otro estado
                if status == 'down' and prev_status != 'down':
                    mname = machines_by_id.get(svc.machine_id).name if svc.machine_id in machines_by_id else None
                    service_down_events.append((svc, prev_status or 'unknown', mname))

            try:
                _prune_checks(db, ServiceCheck, svc.id)
            except Exception:
                pass

        # Heurística: actualizar Machine.status según servicios asociados
        try:
            for m in machines_by_id.values():
                svcs = [s for s in services if s.machine_id == m.id]
                if not svcs:
                    continue
                if any(s.last_status == 'down' for s in svcs):
                    # Si TODOS los servicios de la máquina están down => offline
                    if all(s.last_status == 'down' for s in svcs):
                        m.status = 'offline'
                    else:
                        m.status = 'warning'
                elif any(s.last_status == 'warning' for s in svcs):
                    m.status = 'warning'
                elif all(s.last_status == 'up' for s in svcs):
                    m.status = 'online'
                m.last_seen = now

                # Detectar transición a offline para alertar
                if (prev_machine_status.get(m.id) != 'offline'
                        and m.status == 'offline'):
                    machine_offline_events.append(m)
        except Exception as e:
            logger.warning(f"poll: actualización de Machine.status falló: {e}")

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"poll commit falló: {e}")
            return

        # Disparar notificaciones DESPUÉS del commit (idempotente: cooldown
        # interno de send_email_async evita duplicados si flappea el estado).
        if service_down_events or machine_offline_events:
            try:
                from modules.notifications.dispatch import (
                    notify_service_down, notify_machine_offline,
                )
                for svc, prev, mname in service_down_events:
                    notify_service_down(svc, prev, machine_name=mname)
                for m in machine_offline_events:
                    notify_machine_offline(m)
            except Exception as e:                          # noqa: BLE001
                logger.error(f"poll: notify falló: {e}")


def start_poller(app, interval=POLL_INTERVAL_SEC):
    """Lanza un thread que corre run_poll_cycle cada `interval` segundos."""
    def _loop():
        # Pequeña espera inicial para no chocar con la migración inicial
        time.sleep(5)
        while True:
            try:
                run_poll_cycle(app)
            except Exception as e:
                logger.error(f"Poller falló: {e}")
            time.sleep(interval)

    t = threading.Thread(target=_loop, daemon=True, name='monit-poller')
    t.start()
    logger.info(f"Poller de monitorización iniciado (cada {interval}s)")
    return t
