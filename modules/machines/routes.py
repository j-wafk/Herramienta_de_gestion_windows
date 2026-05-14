import socket
import re
import concurrent.futures
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

from database import db
from database.models import Machine, SystemMetric, Service
from modules.auth.decorators import require_role
from utils.audit import log_action

machines_bp = Blueprint('machines', __name__)

# Acepta IPv4 estricta, IPv6 simplificada (con `:`) o un nombre de host válido.
_IP_RE   = re.compile(r'^\d{1,3}(\.\d{1,3}){3}$')
_HOST_RE = re.compile(r'^[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$')


def _valid_host(value):
    if not value:
        return False
    v = value.strip()
    if _IP_RE.match(v):
        parts = v.split('.')
        return all(0 <= int(p) <= 255 for p in parts)
    if ':' in v:                       # IPv6 — laxo
        return len(v) <= 45
    return bool(_HOST_RE.match(v)) and len(v) <= 100


@machines_bp.route('', methods=['GET'])
def list_machines():
    """Lista todas las máquinas registradas."""
    machines = Machine.query.order_by(Machine.created_at).all()
    return jsonify([m.to_dict() for m in machines])


@machines_bp.route('', methods=['POST'])
@require_role('superadmin', 'admin', 'operador')
def add_machine():
    """Registra una nueva máquina. superadmin, admin u operador."""
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    ip   = (data.get('ip') or '').strip()
    if not name or not ip:
        return jsonify({'error': 'Se requieren los campos name e ip'}), 400
    if len(name) > 100:
        return jsonify({'error': 'name demasiado largo (máx 100)'}), 400
    if not _valid_host(ip):
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

    machine = Machine(name=name, ip=ip, port=port, status='unknown',
                      description=description)
    db.session.add(machine)
    db.session.commit()
    log_action('machine_added', f'machine:{machine.name}',
               f'ip={machine.ip}:{machine.port}',
               machine_id=machine.id)
    return jsonify(machine.to_dict()), 201


@machines_bp.route('/<int:machine_id>', methods=['PUT'])
@require_role('superadmin', 'admin', 'operador')
def update_machine(machine_id):
    """Actualiza nombre/IP/puerto/descripción de una máquina."""
    machine = Machine.query.get_or_404(machine_id)
    data = request.get_json(silent=True) or {}

    if 'name' in data:
        name = (data['name'] or '').strip()
        if not name:
            return jsonify({'error': 'name no puede estar vacío'}), 400
        if len(name) > 100:
            return jsonify({'error': 'name demasiado largo (máx 100)'}), 400
        machine.name = name

    new_ip   = machine.ip
    new_port = machine.port
    if 'ip' in data:
        v = (data['ip'] or '').strip()
        if not _valid_host(v):
            return jsonify({'error': 'IP/hostname no válido'}), 400
        new_ip = v
    if 'port' in data:
        try:
            p = int(data['port'])
        except (TypeError, ValueError):
            return jsonify({'error': 'port debe ser un número'}), 400
        if not (1 <= p <= 65535):
            return jsonify({'error': 'port fuera de rango (1-65535)'}), 400
        new_port = p

    if (new_ip, new_port) != (machine.ip, machine.port):
        clash = Machine.query.filter(
            Machine.ip == new_ip,
            Machine.port == new_port,
            Machine.id != machine.id,
        ).first()
        if clash:
            return jsonify({'error': f'Ya existe una máquina con IP {new_ip}:{new_port}'}), 409
        machine.ip   = new_ip
        machine.port = new_port

    if 'description' in data:
        desc = (data.get('description') or '').strip()
        if len(desc) > 200:
            return jsonify({'error': 'description demasiado larga (máx 200)'}), 400
        machine.description = desc or None

    db.session.commit()
    log_action('machine_updated', f'machine:{machine.name}',
               f'ip={machine.ip}:{machine.port}',
               machine_id=machine.id)
    return jsonify(machine.to_dict())


@machines_bp.route('/<int:machine_id>', methods=['DELETE'])
@require_role('superadmin', 'admin', 'operador')
def delete_machine(machine_id):
    """Elimina una máquina y todos sus datos."""
    machine = Machine.query.get_or_404(machine_id)
    machine_name = machine.name
    db.session.delete(machine)
    db.session.commit()
    log_action('machine_deleted', f'machine_id:{machine_id}', f'name={machine_name}')
    return jsonify({'message': f'Máquina {machine_id} eliminada'})


@machines_bp.route('/<int:machine_id>/metrics', methods=['GET'])
def get_machine_metrics(machine_id):
    """Devuelve el historial de métricas de una máquina."""
    Machine.query.get_or_404(machine_id)
    hours = min(int(request.args.get('hours', 1)), 168)
    since = datetime.utcnow() - timedelta(hours=hours)

    metrics = (
        SystemMetric.query
        .filter(SystemMetric.machine_id == machine_id,
                SystemMetric.timestamp >= since)
        .order_by(SystemMetric.timestamp)
        .all()
    )
    return jsonify([m.to_dict() for m in metrics])


@machines_bp.route('/<int:machine_id>/services', methods=['GET'])
def get_machine_services(machine_id):
    """Devuelve los servicios conocidos de una máquina."""
    Machine.query.get_or_404(machine_id)
    services = Service.query.filter_by(machine_id=machine_id).order_by(Service.name).all()
    return jsonify([s.to_dict() for s in services])


@machines_bp.route('/<int:machine_id>/ping', methods=['POST'])
@require_role('superadmin', 'admin', 'operador')
def ping_machine(machine_id):
    """Comprueba conectividad TCP con la máquina y actualiza su estado en DB."""
    machine = Machine.query.get_or_404(machine_id)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(3)
            result = s.connect_ex((machine.ip, machine.port))
        online = result == 0
    except Exception:
        online = False

    machine.status = 'online' if online else 'offline'
    if online:
        machine.last_seen = datetime.utcnow()
    db.session.commit()
    return jsonify({'id': machine.id, 'status': machine.status})


def _tcp_probe(ip, port, timeout=2.5):
    """Sondeo TCP simple — devuelve True si el puerto está abierto."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((ip, int(port))) == 0
    except Exception:
        return False


@machines_bp.route('/ping_all', methods=['POST'])
@require_role('superadmin', 'admin', 'operador')
def ping_all_machines():
    """Sondea TODAS las máquinas en paralelo y devuelve la lista actualizada.

    Útil al entrar a la página de Monitorización: el usuario ve estados
    actualizados al instante en lugar del último valor cacheado del poller.
    """
    machines = Machine.query.order_by(Machine.created_at).all()
    # Snapshot (id, ip, port) para llamar al hilo sin acoplarlo a la sesión SQLAlchemy
    targets = [(m.id, m.ip, m.port) for m in machines]

    results = {}
    if targets:
        max_workers = min(10, len(targets))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_id = {pool.submit(_tcp_probe, ip, port): mid for (mid, ip, port) in targets}
            for fut in concurrent.futures.as_completed(future_to_id, timeout=10):
                mid = future_to_id[fut]
                try:
                    results[mid] = fut.result()
                except Exception:
                    results[mid] = False

    now = datetime.utcnow()
    for m in machines:
        ok = bool(results.get(m.id, False))
        m.status = 'online' if ok else 'offline'
        if ok:
            m.last_seen = now
    db.session.commit()
    return jsonify([m.to_dict() for m in machines])
