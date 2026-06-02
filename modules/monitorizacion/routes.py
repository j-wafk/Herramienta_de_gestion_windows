"""Endpoints de la página de Monitorización.

- Las máquinas son las MISMAS del modelo `Machine` que usa el selector de
  cabecera (/api/machines), por lo que un alta/edición/baja desde aquí o
  desde el selector se ve reflejada en ambos sitios.
- Los servicios monitorizados son `MonitoredService` (sondeo TCP/UDP/HTTPS).
- La actividad reciente proviene de `ServiceCheck`.
"""
import re
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from database import db
from database.models import Machine, MonitoredService, ServiceCheck
from modules.auth.decorators import require_role
from modules.monitorizacion.probe import probe_service
from utils.audit import log_action

monitorizacion_bp = Blueprint('monitorizacion', __name__)

_IP_RE = re.compile(r'^\d{1,3}(\.\d{1,3}){3}$')
_HOST_RE = re.compile(
    r'^[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$')
_VALID_PROTOS = ('TCP', 'UDP', 'HTTPS')


def _valid_host(value):
    if not value:
        return False
    v = value.strip()
    if _IP_RE.match(v):
        return all(0 <= int(p) <= 255 for p in v.split('.'))
    if ':' in v:
        return len(v) <= 45
    return bool(_HOST_RE.match(v)) and len(v) <= 100


def _icon_key_from_name(name: str) -> str:
    n = (name or '').lower()
    if 'winrm' in n:
        return 'winrm'
    if 'iis' in n or 'web' in n:
        return 'iis'
    if 'sql' in n:
        return 'sql'
    if 'rdp' in n:
        return 'rdp'
    if 'dns' in n:
        return 'dns'
    if 'backup' in n:
        return 'backup'
    if 'ssh' in n:
        return 'ssh'
    if 'http' in n or 'api' in n:
        return 'api'
    return ''


def _record_check(svc: MonitoredService, result: dict, persist_event: bool = True):
    """Aplica el resultado de un sondeo. Crea evento si el estado cambió."""
    prev = svc.last_status
    svc.last_status = result['status']
    svc.last_latency_ms = result.get('latency_ms')
    svc.last_message = result.get('message')
    svc.last_check = datetime.utcnow()
    if persist_event and prev != svc.last_status and svc.last_status != 'unknown':
        db.session.add(ServiceCheck(
            service_id=svc.id,
            timestamp=datetime.utcnow(),
            status=svc.last_status,
            message=svc.last_message,
            latency_ms=svc.last_latency_ms,
        ))


# ───────────────────────────── Resumen ──────────────────────────────
@monitorizacion_bp.route('/summary', methods=['GET'])
def get_summary():
    machines_total = Machine.query.count()
    machines_online = Machine.query.filter(Machine.status == 'online').count()
    services_total = MonitoredService.query.filter_by(enabled=True).count()
    services_up = MonitoredService.query.filter_by(enabled=True, last_status='up').count()
    return jsonify({
        'machines_total':  machines_total,
        'machines_online': machines_online,
        'services_total':  services_total,
        'services_up':     services_up,
    })


# ───────────────────────────── Servicios ────────────────────────────
@monitorizacion_bp.route('/services', methods=['GET'])
def list_services():
    rows = MonitoredService.query.order_by(MonitoredService.created_at).all()
    return jsonify({'services': [r.to_dict() for r in rows]})


@monitorizacion_bp.route('/services', methods=['POST'])
@require_role('superadmin', 'admin')
def create_service():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    ip = (data.get('ip') or '').strip()
    if not name or not ip:
        return jsonify({'error': 'name e ip son obligatorios'}), 400
    if len(name) > 80:
        return jsonify({'error': 'name demasiado largo (máx 80)'}), 400
    if not _valid_host(ip):
        return jsonify({'error': 'IP/hostname no válido'}), 400
    try:
        port = int(data.get('port'))
    except (TypeError, ValueError):
        return jsonify({'error': 'port debe ser un número'}), 400
    if not (1 <= port <= 65535):
        return jsonify({'error': 'port fuera de rango (1-65535)'}), 400
    proto = (data.get('protocol') or 'TCP').upper()
    if proto not in _VALID_PROTOS:
        return jsonify({'error': f'protocol debe ser uno de {_VALID_PROTOS}'}), 400

    machine_id = data.get('machine_id')
    if machine_id is not None and machine_id != '':
        try:
            machine_id = int(machine_id)
        except (TypeError, ValueError):
            return jsonify({'error': 'machine_id no válido'}), 400
        if not Machine.query.get(machine_id):
            return jsonify({'error': f'Máquina {machine_id} no existe'}), 404
    else:
        machine_id = None

    svc = MonitoredService(
        machine_id=machine_id,
        name=name,
        ip=ip,
        port=port,
        protocol=proto,
        enabled=bool(data.get('enabled', True)),
        icon_key=_icon_key_from_name(name) or None,
    )
    db.session.add(svc)
    db.session.flush()                   # asigna svc.id antes del primer evento

    if svc.enabled:
        try:
            res = probe_service(svc.ip, svc.port, svc.protocol)
            _record_check(svc, res, persist_event=False)
            db.session.add(ServiceCheck(
                service_id=svc.id, timestamp=datetime.utcnow(),
                status=svc.last_status, message=svc.last_message,
                latency_ms=svc.last_latency_ms,
            ))
        except Exception:
            pass

    db.session.commit()
    log_action('service_added', f'service:{svc.name}',
               f'{svc.protocol} {svc.ip}:{svc.port}',
               machine_id=svc.machine_id)
    return jsonify(svc.to_dict()), 201


@monitorizacion_bp.route('/services/<int:svc_id>', methods=['PUT'])
@require_role('superadmin', 'admin')
def update_service(svc_id):
    svc = MonitoredService.query.get_or_404(svc_id)
    data = request.get_json(silent=True) or {}

    if 'name' in data:
        v = (data['name'] or '').strip()
        if not v:
            return jsonify({'error': 'name no puede estar vacío'}), 400
        if len(v) > 80:
            return jsonify({'error': 'name demasiado largo'}), 400
        svc.name = v
        svc.icon_key = _icon_key_from_name(v) or None

    if 'ip' in data:
        v = (data['ip'] or '').strip()
        if not _valid_host(v):
            return jsonify({'error': 'IP/hostname no válido'}), 400
        svc.ip = v

    if 'port' in data:
        try:
            p = int(data['port'])
        except (TypeError, ValueError):
            return jsonify({'error': 'port debe ser un número'}), 400
        if not (1 <= p <= 65535):
            return jsonify({'error': 'port fuera de rango'}), 400
        svc.port = p

    if 'protocol' in data:
        proto = (data['protocol'] or 'TCP').upper()
        if proto not in _VALID_PROTOS:
            return jsonify({'error': 'protocol no válido'}), 400
        svc.protocol = proto

    if 'machine_id' in data:
        mid = data.get('machine_id')
        if mid in (None, ''):
            svc.machine_id = None
        else:
            try:
                mid = int(mid)
            except (TypeError, ValueError):
                return jsonify({'error': 'machine_id no válido'}), 400
            if not Machine.query.get(mid):
                return jsonify({'error': f'Máquina {mid} no existe'}), 404
            svc.machine_id = mid

    if 'enabled' in data:
        svc.enabled = bool(data['enabled'])
        if not svc.enabled:
            svc.last_status = 'unknown'

    if svc.enabled:
        try:
            res = probe_service(svc.ip, svc.port, svc.protocol)
            _record_check(svc, res, persist_event=True)
        except Exception:
            pass

    db.session.commit()
    log_action('service_updated', f'service:{svc.name}',
               f'{svc.protocol} {svc.ip}:{svc.port}',
               machine_id=svc.machine_id)
    return jsonify(svc.to_dict())


@monitorizacion_bp.route('/services/<int:svc_id>', methods=['DELETE'])
@require_role('superadmin', 'admin')
def delete_service(svc_id):
    svc = MonitoredService.query.get_or_404(svc_id)
    name = svc.name
    machine_id = svc.machine_id
    db.session.delete(svc)
    db.session.commit()
    log_action('service_deleted', f'service:{name}', f'id={svc_id}',
               machine_id=machine_id)
    return jsonify({'message': f'Servicio {svc_id} eliminado'})


@monitorizacion_bp.route('/services/<int:svc_id>/check', methods=['POST'])
@require_role('superadmin', 'admin', 'operador')
def check_service_now(svc_id):
    """Lanza un sondeo ad-hoc del servicio."""
    svc = MonitoredService.query.get_or_404(svc_id)
    if not svc.enabled:
        return jsonify({'error': 'Servicio deshabilitado'}), 400
    res = probe_service(svc.ip, svc.port, svc.protocol)
    _record_check(svc, res, persist_event=True)
    db.session.commit()
    return jsonify(svc.to_dict())


# ───────────────────────────── Actividad ─────────────────────────────
@monitorizacion_bp.route('/activity', methods=['GET'])
def list_activity():
    try:
        limit = max(1, min(int(request.args.get('limit', 15)), 200))
    except (TypeError, ValueError):
        limit = 15
    since = datetime.utcnow() - timedelta(days=7)
    rows = (
        ServiceCheck.query
        .filter(ServiceCheck.timestamp >= since)
        .order_by(ServiceCheck.timestamp.desc())
        .limit(limit)
        .all()
    )
    return jsonify({'events': [r.to_dict() for r in rows]})


# ─────────────── Máquinas (misma tabla `Machine` que /api/machines) ─
# Los endpoints replican el comportamiento del blueprint de machines para
# que la página haga CRUD sin tener que cambiar el JS. Internamente comparten
# el modelo Machine: el selector superior y la tabla aquí ven los MISMOS
# datos siempre.

def _machines_valid_host(v):
    from modules.machines.routes import _valid_host as vh
    return vh(v)


@monitorizacion_bp.route('/machines', methods=['POST'])
@require_role('superadmin', 'admin', 'operador')
def add_machine():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    ip = (data.get('ip') or '').strip()
    if not name or not ip:
        return jsonify({'error': 'name e ip son obligatorios'}), 400
    if not _machines_valid_host(ip):
        return jsonify({'error': 'IP/hostname no válido'}), 400
    try:
        port = int(data.get('port', 12345))
    except (TypeError, ValueError):
        return jsonify({'error': 'port debe ser un número'}), 400
    if not (1 <= port <= 65535):
        return jsonify({'error': 'port fuera de rango (1-65535)'}), 400
    description = (data.get('description') or '').strip() or None
    if description and len(description) > 200:
        return jsonify({'error': 'description demasiado larga (máx 200)'}), 400

    if Machine.query.filter_by(ip=ip, port=port).first():
        return jsonify({'error': f'Ya existe una máquina con IP {ip}:{port}'}), 409

    m = Machine(name=name, ip=ip, port=port, description=description, status='unknown')
    db.session.add(m)
    db.session.commit()
    log_action('machine_added', f'machine:{m.name}',
               f'ip={m.ip}:{m.port}', machine_id=m.id)
    return jsonify(m.to_dict()), 201


@monitorizacion_bp.route('/machines/<int:machine_id>', methods=['PUT'])
@require_role('superadmin', 'admin', 'operador')
def update_machine(machine_id):
    m = Machine.query.get_or_404(machine_id)
    data = request.get_json(silent=True) or {}

    if 'name' in data:
        v = (data['name'] or '').strip()
        if not v:
            return jsonify({'error': 'name no puede estar vacío'}), 400
        if len(v) > 100:
            return jsonify({'error': 'name demasiado largo'}), 400
        m.name = v

    new_ip = m.ip
    new_port = m.port
    if 'ip' in data:
        v = (data['ip'] or '').strip()
        if not _machines_valid_host(v):
            return jsonify({'error': 'IP/hostname no válido'}), 400
        new_ip = v
    if 'port' in data:
        try:
            p = int(data['port'])
        except (TypeError, ValueError):
            return jsonify({'error': 'port debe ser un número'}), 400
        if not (1 <= p <= 65535):
            return jsonify({'error': 'port fuera de rango'}), 400
        new_port = p
    if (new_ip, new_port) != (m.ip, m.port):
        clash = Machine.query.filter(
            Machine.ip == new_ip,
            Machine.port == new_port,
            Machine.id != m.id,
        ).first()
        if clash:
            return jsonify({'error': f'Ya existe una máquina con IP {new_ip}:{new_port}'}), 409
        m.ip = new_ip
        m.port = new_port

    if 'description' in data:
        v = (data.get('description') or '').strip()
        if len(v) > 200:
            return jsonify({'error': 'description demasiado larga'}), 400
        m.description = v or None

    db.session.commit()
    log_action('machine_updated', f'machine:{m.name}',
               f'ip={m.ip}:{m.port}', machine_id=m.id)
    return jsonify(m.to_dict())


@monitorizacion_bp.route('/machines/<int:machine_id>', methods=['DELETE'])
@require_role('superadmin', 'admin', 'operador')
def delete_machine(machine_id):
    m = Machine.query.get_or_404(machine_id)
    name = m.name
    db.session.delete(m)
    db.session.commit()
    log_action('machine_deleted', f'machine_id:{machine_id}', f'name={name}')
    return jsonify({'message': f'Máquina {machine_id} eliminada'})
