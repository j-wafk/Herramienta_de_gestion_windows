from flask import Blueprint, jsonify, request
from flask_login import current_user
from utils.powershell_client import resolve_and_send
from utils.validators import validate_network_target, validate_adapter_name

red_bp = Blueprint('red', __name__)

_TOOLS_OPERADOR = {'ping', 'traceroute', 'ipconfig', 'netstat'}
_TOOLS_ADMIN    = {'release_renew', 'flush_dns'}


def _mid():
    mid = request.args.get('machine_id')
    if not mid and request.is_json:
        mid = (request.get_json(silent=True) or {}).get('machine_id')
    return mid or None


def _send(command):
    return resolve_and_send(command, _mid())


def _parse_kv(text):
    text = (text or '').lstrip('﻿').lstrip('﻿')
    data = {}
    for line in text.strip().splitlines():
        if ': ' in line:
            k, v = line.split(': ', 1)
            data[k.strip()] = v.strip()
    return data


def _parse_pipe_table(text):
    text = (text or '').lstrip('﻿').lstrip('﻿').strip()
    if not text:
        return [], []
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return [], []
    headers = [h.strip() for h in lines[0].split('|')]
    rows = []
    for line in lines[1:]:
        parts = [p.strip() for p in line.split('|')]
        row = {headers[i]: parts[i] if i < len(parts) else '' for i in range(len(headers))}
        rows.append(row)
    return headers, rows


@red_bp.route('/adapters', methods=['GET'])
def get_adapters():
    raw = _send('net_adapters')
    _, rows = _parse_pipe_table(raw)
    return jsonify({'adapters': rows})


@red_bp.route('/adapter_details', methods=['GET'])
def get_adapter_details():
    adapter = request.args.get('adapter', '').strip()
    if not adapter:
        return jsonify({})
    try:
        adapter = validate_adapter_name(adapter)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    raw = _send(f'net_adapter_details {adapter}')
    return jsonify(_parse_kv(raw))


@red_bp.route('/stats', methods=['GET'])
def get_network_stats():
    raw = _send('net_stats')
    _, rows = _parse_pipe_table(raw)
    return jsonify({'stats': rows})


@red_bp.route('/activity', methods=['GET'])
def get_network_activity():
    raw = _send('net_activity')
    events = []
    for line in (raw or '').lstrip('﻿').strip().splitlines():
        parts = line.split('|', 3)
        if len(parts) >= 2:
            events.append({
                'time':    parts[0].strip(),
                'type':    parts[1].strip(),
                'source':  parts[2].strip() if len(parts) > 2 else '',
                'message': parts[3].strip() if len(parts) > 3 else (parts[2].strip() if len(parts) > 2 else ''),
            })
    return jsonify({'events': events})


@red_bp.route('/alerts', methods=['GET'])
def get_network_alerts():
    raw = _send('net_alerts')
    alerts = []
    for line in (raw or '').lstrip('﻿').strip().splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split('|', 2)]
        alerts.append({
            'status':  parts[0] if len(parts) > 0 else 'info',
            'message': parts[1] if len(parts) > 1 else line,
            'badge':   parts[2] if len(parts) > 2 else '',
        })
    return jsonify({'alerts': alerts})


@red_bp.route('/tool', methods=['POST'])
def run_network_tool():
    data = request.get_json(silent=True) or {}
    tool   = data.get('tool', '').strip()
    target = data.get('target', '').strip()

    all_tools = _TOOLS_OPERADOR | _TOOLS_ADMIN
    if tool not in all_tools:
        return jsonify({'error': 'Herramienta no reconocida'}), 400

    # Verificar permisos por herramienta
    role = current_user.role if current_user.is_authenticated else None
    if tool in _TOOLS_ADMIN and role not in ('superadmin', 'admin'):
        return jsonify({'error': 'Permiso denegado para esta herramienta'}), 403
    if tool in _TOOLS_OPERADOR and role == 'solo_lectura':
        return jsonify({'error': 'Permiso denegado'}), 403

    # Validar target para herramientas que lo usan
    if tool in ('ping', 'traceroute'):
        try:
            target = validate_network_target(target)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

    tool_map = {
        'ping':          f'net_ping {target}',
        'traceroute':    f'net_traceroute {target}',
        'ipconfig':      'net_ipconfig',
        'netstat':       'net_netstat',
        'release_renew': 'net_release_renew',
        'flush_dns':     'net_flush_dns',
    }

    result = _send(tool_map[tool])
    return jsonify({'output': result or 'Sin respuesta del servidor.', 'tool': tool})
