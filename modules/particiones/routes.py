# modules/particiones/routes.py
from flask import Blueprint, request, jsonify, current_app
from utils.powershell_client import resolve_and_send
from .parsers import (
    parse_physical_disks_output, parse_partitions_output,
    parse_disk_detail_output, compute_disk_usage_from_partitions,
)
import logging
from modules.auth.decorators import require_role
from utils.validators import (
    validate_disk_id, validate_partition_id, validate_numeric,
    validate_safe_name, validate_enum, validate_drive_letter,
    ALLOWED_FILESYSTEMS,
)
from utils.audit import log_action

logger = logging.getLogger(__name__)

particiones_bp = Blueprint('particiones', __name__)


def _mid():
    mid = request.args.get('machine_id')
    if not mid and request.is_json:
        mid = (request.get_json(silent=True) or {}).get('machine_id')
    return mid or None


def _send(command):
    return resolve_and_send(command, _mid())


@particiones_bp.route('/disks', methods=['GET'])
def get_physical_disks():
    try:
        machine_id = _mid()
        cache_manager = current_app.cache_manager

        if not machine_id and cache_manager.is_cache_valid("disks"):
            return jsonify(cache_manager.get_cache_data("disks"))

        output = _send('list_disks')

        if not output or "Error" in output:
            logger.error(f"Error al obtener discos: {output}")
            return jsonify({"error": "Error al obtener lista de discos físicos"}), 500

        disks = parse_physical_disks_output(output)

        # Enriquecer con uso real desde las particiones
        try:
            parts_out = _send('list_partitions')
            if parts_out and "Error" not in parts_out:
                parts = parse_partitions_output(parts_out)
                by_disk = {}
                for p in parts:
                    by_disk.setdefault(p["disk_id"], []).append(p)
                compute_disk_usage_from_partitions(disks, by_disk)
        except Exception as e:
            logger.warning(f"No se pudo enriquecer discos con uso real: {e}")

        if not machine_id:
            cache_manager.update_cache("disks", disks)

        return jsonify(disks)
    except Exception as e:
        logger.error(f"Error en /disks: {e}")
        return jsonify({"error": "Error interno del servidor"}), 500


@particiones_bp.route('/partitions', methods=['GET'])
def get_partitions():
    try:
        disk_id = request.args.get('disk_id')
        machine_id = _mid()
        cache_manager = current_app.cache_manager

        # Validar disk_id si se proporciona (solo lectura, pero evita inyección)
        if disk_id:
            try:
                disk_id = validate_disk_id(disk_id)
            except ValueError as e:
                return jsonify({"error": str(e)}), 400

        if not machine_id and cache_manager.is_cache_valid("partitions"):
            partitions_data = cache_manager.get_cache_data("partitions")
        else:
            output = _send('list_partitions')

            if not output or "Error" in output:
                logger.error(f"Error al obtener particiones: {output}")
                return jsonify({"error": "Error al obtener lista de particiones"}), 500

            partitions = parse_partitions_output(output)
            partitions_by_disk = {}
            for p in partitions:
                key = p["disk_id"]
                partitions_by_disk.setdefault(key, []).append(p)

            if not machine_id:
                cache_manager.update_cache("partitions", partitions_by_disk)
            partitions_data = partitions_by_disk

        if disk_id:
            disk_num = disk_id.replace('disk', '')
            return jsonify(partitions_data.get(disk_num, []))

        all_partitions = [p for ps in partitions_data.values() for p in ps]
        return jsonify(all_partitions)
    except Exception as e:
        logger.error(f"Error en /partitions: {e}")
        return jsonify({"error": "Error interno del servidor"}), 500


@particiones_bp.route('/disk_detail', methods=['GET'])
def get_disk_detail():
    try:
        disk_id = request.args.get('disk_id')
        if not disk_id:
            return jsonify({"error": "Se requiere disk_id"}), 400

        try:
            disk_id = validate_disk_id(disk_id)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        output = _send(f'disk_detail {disk_id}')

        if not output or "Error" in output:
            return jsonify({"error": f"Error al obtener detalles del disco {disk_id}"}), 500

        return jsonify(parse_disk_detail_output(output, disk_id))
    except Exception as e:
        logger.error(f"Error en /disk_detail: {e}")
        return jsonify({"error": "Error interno del servidor"}), 500


@particiones_bp.route('/partition_operation', methods=['POST'])
@require_role('superadmin', 'admin')
def execute_partition_operation():
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No se proporcionaron datos"}), 400

        operation = data.get('operation')
        if not operation:
            return jsonify({"error": "No se proporcionó operación"}), 400

        command = None
        try:
            if operation == 'create':
                disk_id    = validate_disk_id(data.get('disk_id'))
                size       = validate_numeric(data.get('size'), 'size', min_val=0.1, max_val=65536)
                filesystem = validate_enum(data.get('filesystem'), ALLOWED_FILESYSTEMS, 'filesystem')
                label      = validate_safe_name(data.get('label', 'Nueva'), 'label') if data.get('label') else ''
                letter     = validate_drive_letter(data.get('letter', ''))
                # Construir comando: si hay letra, label se vuelve obligatorio (placeholder
                # vacío entre comillas) para mantener orden posicional.
                parts = [f'create_partition {disk_id} {size} {filesystem}']
                if label or letter:
                    parts.append(f'"{label}"' if label else '""')
                if letter:
                    parts.append(letter)
                command = ' '.join(parts)

            elif operation == 'format':
                partition_id = validate_partition_id(data.get('partition_id'))
                filesystem   = validate_enum(data.get('filesystem'), ALLOWED_FILESYSTEMS, 'filesystem')
                label        = validate_safe_name(data.get('label', 'Volumen'), 'label') if data.get('label') else ''
                command = (
                    f'format_partition {partition_id} {filesystem} "{label}"'
                    if label else
                    f'format_partition {partition_id} {filesystem}'
                )

            elif operation == 'delete':
                partition_id = validate_partition_id(data.get('partition_id'))
                command = f'delete_partition {partition_id}'

            elif operation == 'resize':
                partition_id = validate_partition_id(data.get('partition_id'))
                new_size     = validate_numeric(data.get('new_size'), 'new_size', min_val=0.1, max_val=65536)
                command = f'resize_partition {partition_id} {new_size}'

            else:
                return jsonify({"error": f"Operación no válida: {operation}"}), 400

        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        output = _send(command)
        log_action('partition_op', operation, f'cmd={command}', machine_id=_mid())

        cache_manager = current_app.cache_manager
        cache_manager.update_cache("disks", [])
        cache_manager.update_cache("partitions", {})

        return jsonify({"output": output})
    except Exception as e:
        logger.error(f"Error en /partition_operation: {e}")
        return jsonify({"error": "Error interno del servidor"}), 500
