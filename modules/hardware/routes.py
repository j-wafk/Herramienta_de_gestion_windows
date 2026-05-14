# modules/hardware/routes.py
import json
from datetime import datetime
from flask import Blueprint, jsonify, request, Response, current_app
from utils.powershell_client import resolve_and_send, send_command_to_powershell
from config import Config
from modules.auth.decorators import require_role

hardware_bp = Blueprint('hardware', __name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def _mid():
    mid = request.args.get('machine_id')
    if not mid and request.is_json:
        mid = (request.get_json(silent=True) or {}).get('machine_id')
    return mid or None


def _send(command):
    return resolve_and_send(command, _mid())


def _parse_kv(text):
    """Parse 'key: value' lines into a dict, stripping UTF-8 BOM if present."""
    text = (text or '').lstrip('﻿')
    data = {}
    for line in text.strip().splitlines():
        if ': ' in line:
            k, v = line.split(': ', 1)
            data[k.strip()] = v.strip()
    return data


def _parse_pipe(text):
    """Parse pipe-delimited table into list of dicts, stripping BOM."""
    text = (text or '').lstrip('﻿')
    lines = text.strip().splitlines()
    if not lines:
        return []
    headers = [h.strip() for h in lines[0].split('|')]
    rows = []
    for line in lines[1:]:
        line = line.strip()
        if not line or '|' not in line:
            continue
        parts = line.split('|')
        row = {h: (parts[i].strip() if i < len(parts) else '') for i, h in enumerate(headers)}
        rows.append(row)
    return rows


def _get_local_machine():
    from database.models import Machine
    return Machine.query.filter_by(
        ip=Config.POWERSHELL_SERVER,
        port=Config.POWERSHELL_PORT,
    ).first()


def _get_machine(machine_id=None):
    from database.models import Machine
    if machine_id:
        return Machine.query.get(int(machine_id))
    return _get_local_machine()


# ── live fetch helpers ────────────────────────────────────────────────────────

def _fetch_system():
    return _parse_kv(_send('hardware_system'))


def _fetch_cpu():
    data = _parse_kv(_send('hardware_cpu'))
    for field in ('cores', 'threads', 'sockets'):
        if field in data:
            try:
                data[field] = int(data[field])
            except (ValueError, TypeError):
                pass
    return data


def _fetch_memory():
    data = _parse_kv(_send('hardware_memory'))
    for field in ('total_gb', 'used_gb', 'free_gb', 'speed', 'slots_used', 'slots_total'):
        if field in data:
            try:
                data[field] = float(str(data[field]).replace(',', '.'))
            except (ValueError, TypeError):
                pass
    return data


def _fetch_disks():
    rows = _parse_pipe(_send('hardware_disks'))
    disks = []
    for r in rows:
        disk = {
            'model':       r.get('model', '-'),
            'type':        r.get('type', '-'),
            'status':      r.get('status', '-'),
            'temperature': r.get('temperature', '-'),
        }
        for field in ('capacity_gb', 'used_gb', 'used_pct'):
            try:
                disk[field] = float(r.get(field, '0').replace(',', '.'))
            except (ValueError, TypeError):
                disk[field] = 0.0
        disks.append(disk)
    return disks


def _fetch_gpu():
    return _parse_pipe(_send('hardware_gpu'))


def _fetch_motherboard():
    return _parse_kv(_send('hardware_motherboard'))


def _fetch_devices():
    return _parse_pipe(_send('hardware_devices'))


# ── snapshot DB helpers ───────────────────────────────────────────────────────

def _save_snapshot(machine, sys_data, cpu_data, mem_data, disks, gpu, mb, devices):
    from database.models import HardwareSnapshot
    from database import db

    snap = HardwareSnapshot.query.filter_by(machine_id=machine.id).first()
    if snap is None:
        snap = HardwareSnapshot(machine_id=machine.id)
        db.session.add(snap)

    snap.timestamp        = datetime.utcnow()
    snap.system_json      = json.dumps(sys_data,  ensure_ascii=False)
    snap.cpu_json         = json.dumps(cpu_data,  ensure_ascii=False)
    snap.memory_json      = json.dumps(mem_data,  ensure_ascii=False)
    snap.disks_json       = json.dumps(disks,     ensure_ascii=False)
    snap.gpu_json         = json.dumps(gpu,       ensure_ascii=False)
    snap.motherboard_json = json.dumps(mb,        ensure_ascii=False)
    snap.devices_json     = json.dumps(devices,   ensure_ascii=False)
    db.session.commit()
    return snap


# ── endpoints ─────────────────────────────────────────────────────────────────

@hardware_bp.route('/snapshot', methods=['GET'])
def get_snapshot():
    """Load the latest hardware snapshot from DB (no PowerShell call)."""
    machine = _get_machine(_mid())
    if not machine:
        return jsonify({'error': 'Máquina no encontrada'}), 404

    from database.models import HardwareSnapshot
    snap = HardwareSnapshot.query.filter_by(machine_id=machine.id).first()
    if not snap:
        return jsonify({'empty': True}), 200

    return jsonify(snap.to_dict())


@hardware_bp.route('/refresh', methods=['POST'])
@require_role('superadmin', 'admin', 'operador')
def refresh_hardware():
    """Fetch live hardware data from PowerShell, save to DB, return it."""
    machine = _get_machine(_mid())
    if not machine:
        return jsonify({'error': 'Máquina no encontrada'}), 404

    sys_data = _fetch_system()
    cpu_data = _fetch_cpu()
    mem_data = _fetch_memory()
    disks    = _fetch_disks()
    gpu      = _fetch_gpu()
    mb       = _fetch_motherboard()
    devices  = _fetch_devices()

    snap = _save_snapshot(machine, sys_data, cpu_data, mem_data, disks, gpu, mb, devices)
    return jsonify(snap.to_dict())


@hardware_bp.route('/memory/live', methods=['GET'])
def get_memory_live():
    """Live RAM usage (lightweight, no DB, for 30-second polling)."""
    data = _fetch_memory()
    return jsonify(data)


# ── individual live endpoints (kept for export and machine-specific use) ──────

@hardware_bp.route('/system', methods=['GET'])
def get_hardware_system():
    return jsonify(_fetch_system())


@hardware_bp.route('/info', methods=['GET'])
def get_hardware_info():
    return jsonify(_fetch_system())


@hardware_bp.route('/cpu', methods=['GET'])
def get_hardware_cpu():
    return jsonify(_fetch_cpu())


@hardware_bp.route('/memory', methods=['GET'])
def get_hardware_memory():
    return jsonify(_fetch_memory())


@hardware_bp.route('/disks', methods=['GET'])
def get_hardware_disks():
    return jsonify({'disks': _fetch_disks()})


@hardware_bp.route('/gpu', methods=['GET'])
def get_hardware_gpu():
    return jsonify({'gpus': _fetch_gpu()})


@hardware_bp.route('/motherboard', methods=['GET'])
def get_hardware_motherboard():
    return jsonify(_fetch_motherboard())


@hardware_bp.route('/devices', methods=['GET'])
def get_hardware_devices():
    return jsonify({'devices': _fetch_devices()})


@hardware_bp.route('/export', methods=['GET'])
def export_hardware():
    machine = _get_machine(_mid())
    report = {'exported_at': datetime.now().isoformat()}

    if machine:
        from database.models import HardwareSnapshot
        snap = HardwareSnapshot.query.filter_by(machine_id=machine.id).first()
        if snap:
            report.update(snap.to_dict())
        else:
            report.update({'system': _fetch_system(), 'cpu': _fetch_cpu(), 'memory': _fetch_memory()})
    else:
        report.update({'system': _fetch_system(), 'cpu': _fetch_cpu(), 'memory': _fetch_memory()})

    return Response(
        json.dumps(report, ensure_ascii=False, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': 'attachment; filename=hardware_report.json'},
    )
