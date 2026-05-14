# modules/rendimiento/routes.py
from flask import Blueprint, jsonify, request, current_app
import re
import time
from datetime import datetime, timedelta
from utils.powershell_client import resolve_and_send, send_command_to_powershell
from .parsers import parse_cpu_output, parse_memory_output, parse_process_output
from config import Config
from modules.auth.decorators import require_role

rendimiento_bp = Blueprint('rendimiento', __name__)


def _mid():
    """Devuelve machine_id del request (GET args o POST json)."""
    mid = request.args.get('machine_id')
    if not mid and request.is_json:
        mid = (request.get_json(silent=True) or {}).get('machine_id')
    return mid or None


def _send(command):
    """Envía comando a la máquina activa en el request."""
    return resolve_and_send(command, _mid())


# ── Rendimiento clásico ────────────────────────────────────────

@rendimiento_bp.route('/system', methods=['GET'])
def get_system_data():
    machine_id = _mid()
    cache_manager = current_app.cache_manager

    if machine_id:
        # Datos en tiempo real de la máquina remota — sin caché
        from utils.powershell_client import send_command_to_machine
        from database.models import Machine
        from utils.background_tasks import parse_cpu_output as _cpu, parse_memory_output as _mem, parse_disk_output as _disk
        try:
            machine = Machine.query.get(int(machine_id))
            if not machine:
                return jsonify({"error": f"Máquina {machine_id} no encontrada"}), 404
            cpu_raw  = send_command_to_machine('cpu',    machine.ip, machine.port)
            mem_raw  = send_command_to_machine('memory', machine.ip, machine.port)
            disk_raw = send_command_to_machine('disk',   machine.ip, machine.port)
            reachable = "No se pudo conectar" not in cpu_raw
            return jsonify({
                "cpu":     {"value": _cpu(cpu_raw),  "history": [_cpu(cpu_raw)]  * 15},
                "memory":  {"value": _mem(mem_raw),  "history": [_mem(mem_raw)]  * 15},
                "disk":    _disk(disk_raw),
                "processes": [],
                "machine": {"id": machine.id, "name": machine.name,
                            "ip": machine.ip, "reachable": reachable},
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # Máquina local — usar caché
    if not cache_manager.is_cache_valid("cpu"):
        cache_manager.update_cache("cpu", parse_cpu_output(send_command_to_powershell('cpu')))
    if not cache_manager.is_cache_valid("memory"):
        cache_manager.update_cache("memory", parse_memory_output(send_command_to_powershell('memory')))
    if not cache_manager.is_cache_valid("processes"):
        cache_manager.update_cache("processes", parse_process_output(send_command_to_powershell('process')))
    return jsonify(cache_manager.get_all_system_data())


def _is_reachable(raw):
    """True si la respuesta del PS no es un error de conexión."""
    if not raw:
        return False
    low = raw.lower()
    return ('no se pudo conectar' not in low) and ('error conectando' not in low)


def _active_machine_id():
    """Devuelve el id de la Machine activa: la pasada como machine_id o la 'Local'."""
    mid = _mid()
    if mid:
        try:
            return int(mid)
        except (TypeError, ValueError):
            return None
    from database.models import Machine
    local = Machine.query.filter_by(
        ip=Config.POWERSHELL_SERVER,
        port=Config.POWERSHELL_PORT
    ).first()
    return local.id if local else None


def _history_from_db(machine_id, field, minutes=15):
    """Devuelve una lista de `minutes` valores (uno por minuto) extraída de
    SystemMetric para la máquina indicada.

    - field: 'cpu', 'memory', 'disk_used', 'disk_free'
    - Si varios samples caen dentro del mismo minuto, se hace la media.
    - Si hay menos muestras que `minutes`, se rellena con 0 al principio
      (los huecos antiguos quedan a 0; el más reciente siempre al final).
    """
    if not machine_id:
        return [0] * minutes
    from database.models import SystemMetric
    since = datetime.utcnow() - timedelta(minutes=minutes)
    rows = (SystemMetric.query
            .filter(SystemMetric.machine_id == machine_id,
                    SystemMetric.timestamp >= since)
            .order_by(SystemMetric.timestamp)
            .all())
    # Agrupar por minuto (truncado a YYYY-MM-DD HH:MM)
    buckets = {}
    for r in rows:
        val = getattr(r, field, None)
        if val is None:
            continue
        key = r.timestamp.replace(second=0, microsecond=0)
        buckets.setdefault(key, []).append(float(val))
    # Reconstruir los últimos `minutes` minutos terminados ahora
    now_minute = datetime.utcnow().replace(second=0, microsecond=0)
    history = []
    for i in range(minutes - 1, -1, -1):
        k = now_minute - timedelta(minutes=i)
        vals = buckets.get(k)
        if vals:
            history.append(round(sum(vals) / len(vals), 1))
        else:
            history.append(0.0)
    return history


@rendimiento_bp.route('/cpu', methods=['GET'])
def get_cpu_data():
    machine_id = _mid()
    active_id  = _active_machine_id()
    history    = _history_from_db(active_id, 'cpu', minutes=15)
    if machine_id:
        raw = _send('cpu')
        val = parse_cpu_output(raw)
        reachable = _is_reachable(raw)
    else:
        cache_manager = current_app.cache_manager
        if not cache_manager.is_cache_valid("cpu"):
            cache_manager.update_cache("cpu", parse_cpu_output(send_command_to_powershell('cpu')))
        val = cache_manager.get_cache_data("cpu").get("value", 0)
        reachable = True

    # El valor vivo siempre va al final del array (sustituye el último minuto)
    if history:
        history[-1] = round(float(val), 1)
    return jsonify({"value": val, "history": history, "reachable": reachable})


@rendimiento_bp.route('/memory', methods=['GET'])
def get_memory_data():
    machine_id = _mid()
    active_id  = _active_machine_id()
    history    = _history_from_db(active_id, 'memory', minutes=15)
    if machine_id:
        raw = _send('memory')
        val = parse_memory_output(raw)
        reachable = _is_reachable(raw)
    else:
        cache_manager = current_app.cache_manager
        if not cache_manager.is_cache_valid("memory"):
            cache_manager.update_cache("memory", parse_memory_output(send_command_to_powershell('memory')))
        val = cache_manager.get_cache_data("memory").get("value", 0)
        reachable = True

    if history:
        history[-1] = round(float(val), 1)
    return jsonify({"value": val, "history": history, "reachable": reachable})


@rendimiento_bp.route('/memory_detail', methods=['GET'])
def get_memory_detail():
    output = _send('memory')
    pct = used_gb = total_gb = 0.0
    m = re.search(
        r'memoria:\s*(\d+(?:\.\d+)?)%.*?Usado:\s*(\d+(?:\.\d+)?)\s*GB.*?Total:\s*(\d+(?:\.\d+)?)\s*GB',
        output, re.IGNORECASE)
    if m:
        pct, used_gb, total_gb = float(m.group(1)), float(m.group(2)), float(m.group(3))
    else:
        m2 = re.search(r'(\d+(?:\.\d+)?)%', output)
        if m2:
            pct = float(m2.group(1))
    return jsonify({"pct": pct, "used_gb": used_gb, "total_gb": total_gb})


@rendimiento_bp.route('/processes', methods=['GET'])
def get_processes_data():
    machine_id = _mid()
    if machine_id:
        raw = _send('process')
        return jsonify(parse_process_output(raw))

    cache_manager = current_app.cache_manager

    # Serve from cache if still valid — avoids blocking on the slow PS command
    if cache_manager.is_cache_valid("processes"):
        cached = cache_manager.get_cache_data("processes")
        if cached:
            return jsonify(cached)

    # Cache stale or empty: fetch fresh and store
    raw    = send_command_to_powershell('process')
    parsed = parse_process_output(raw)
    if parsed:
        cache_manager.update_cache("processes", parsed)
        return jsonify(parsed)

    # Parser returned nothing — fall back to whatever is in cache
    cached = cache_manager.get_cache_data("processes")
    return jsonify(cached if cached else [])


@rendimiento_bp.route('/process/kill', methods=['POST'])
@require_role('superadmin', 'admin')
def kill_process():
    data = request.json
    if not data or 'pid' not in data:
        return jsonify({"error": "No se proporcionó PID"}), 400
    output = _send(f'matar {data["pid"]}')
    current_app.cache_manager.cache["processes"]["timestamp"] = 0
    return jsonify({"output": output, "success": True})


@rendimiento_bp.route('/process/start', methods=['POST'])
@require_role('superadmin', 'admin')
def start_process():
    data = request.json
    if not data or 'comando' not in data:
        return jsonify({"error": "No se proporcionó comando"}), 400
    output = _send(f'iniciar {data["comando"]}')
    current_app.cache_manager.cache["processes"]["timestamp"] = 0
    return jsonify({"output": output, "success": True})


@rendimiento_bp.route('/network', methods=['GET'])
def get_network_data():
    return jsonify({"output": _send('network')})


@rendimiento_bp.route('/services', methods=['GET'])
def get_services_data():
    return jsonify({"output": _send('servicios')})


@rendimiento_bp.route('/logs', methods=['GET'])
def get_system_logs():
    return jsonify({"output": _send('log')})


# ── Vista General ──────────────────────────────────────────────

def _parse_kv(text):
    """Parse 'key: value' lines into a dict, stripping UTF-8 BOM if present."""
    text = (text or '').lstrip('﻿')
    data = {}
    for line in text.strip().splitlines():
        if ': ' in line:
            k, v = line.split(': ', 1)
            data[k.strip()] = v.strip()
    return data


@rendimiento_bp.route('/system_info', methods=['GET'])
def get_system_info():
    return jsonify(_parse_kv(_send('system_info')))


@rendimiento_bp.route('/services_status', methods=['GET'])
def get_services_status():
    output = (_send('services_status') or '').lstrip('﻿')
    services = []
    for line in output.strip().splitlines():
        if ': ' in line:
            name, status = line.split(': ', 1)
            services.append({"name": name.strip(), "status": status.strip()})
    return jsonify({"services": services})


@rendimiento_bp.route('/security_status', methods=['GET'])
def get_security_status():
    return jsonify(_parse_kv(_send('security_status')))


@rendimiento_bp.route('/disk_summary', methods=['GET'])
def get_disk_summary():
    output = (_send('disk_summary') or '').lstrip('﻿')
    data = {}
    for line in output.strip().splitlines():
        if ': ' in line:
            k, v = line.split(': ', 1)
            try:
                data[k.strip()] = float(v.strip())
            except ValueError:
                data[k.strip()] = v.strip()
    if not data:
        data = {"used_pct": 35, "free_pct": 65, "free_gb": 0, "total_gb": 0, "used_gb": 0}
    # History real del % usado para que la barra "Disco" del panel "Rendimiento
    # General" muestre evolución y no se quede en --%
    active_id = _active_machine_id()
    hist = _history_from_db(active_id, 'disk_used', minutes=15)
    if hist:
        hist[-1] = round(float(data.get('used_pct', 0)), 1)
    data['history'] = hist
    return jsonify(data)


@rendimiento_bp.route('/recent_activity', methods=['GET'])
def get_recent_activity():
    output = _send('recent_activity')
    events = []
    for line in output.strip().splitlines():
        parts = line.split('|', 3)
        if len(parts) == 4:
            events.append({"time": parts[0], "type": parts[1],
                           "source": parts[2], "message": parts[3]})
    return jsonify({"events": events})


@rendimiento_bp.route('/disk_list', methods=['GET'])
def get_disk_list():
    output = _send('disk_list')
    disks = []
    for i, line in enumerate(output.strip().splitlines()):
        if i == 0 or '|' not in line:
            continue
        parts = line.split('|')
        if len(parts) < 6:
            continue
        try:
            disks.append({
                'letter':   parts[0].strip(),
                'label':    parts[1].strip(),
                'total_gb': float(parts[2].replace(',', '.')),
                'used_gb':  float(parts[3].replace(',', '.')),
                'free_gb':  float(parts[4].replace(',', '.')),
                'used_pct': float(parts[5].replace(',', '.')),
            })
        except (ValueError, IndexError):
            continue
    total = sum(d['total_gb'] for d in disks)
    used  = sum(d['used_gb']  for d in disks)
    free  = sum(d['free_gb']  for d in disks)
    return jsonify({
        'disks': disks,
        'totals': {
            'total_gb': round(total, 2),
            'used_gb':  round(used, 2),
            'free_gb':  round(free, 2),
            'used_pct': round((used / total) * 100, 2) if total > 0 else 0,
        }
    })


@rendimiento_bp.route('/network_stats', methods=['GET'])
def get_network_stats():
    output = _send('network_stats')
    data = {"usage_pct": 0, "down_bps": 0, "up_bps": 0, "link_bps": 0, "output": output}
    for line in output.strip().splitlines():
        if ':' not in line:
            continue
        key, _, val = line.partition(':')
        key = key.strip()
        val = val.strip()
        if key in ('usage_pct', 'down_bps', 'up_bps', 'link_bps'):
            try:
                data[key] = float(val) if key == 'usage_pct' else int(float(val))
            except (ValueError, IndexError):
                pass
    return jsonify(data)


# ── Historial (siempre local, BD) ─────────────────────────────

@rendimiento_bp.route('/history', methods=['GET'])
def get_metrics_history():
    from database.models import Machine, SystemMetric

    hours = min(int(request.args.get('hours', 1)), 168)
    since = datetime.utcnow() - timedelta(hours=hours)
    machine_id = request.args.get('machine_id')

    if machine_id:
        machine = Machine.query.get(machine_id)
    else:
        machine = Machine.query.filter_by(
            ip=Config.POWERSHELL_SERVER,
            port=Config.POWERSHELL_PORT
        ).first()

    if not machine:
        return jsonify({'error': 'Máquina no encontrada'}), 404

    metrics = (
        SystemMetric.query
        .filter(SystemMetric.machine_id == machine.id,
                SystemMetric.timestamp >= since)
        .order_by(SystemMetric.timestamp)
        .all()
    )
    return jsonify({
        'machine': machine.to_dict(),
        'hours': hours,
        'count': len(metrics),
        'metrics': [m.to_dict() for m in metrics],
    })
