# compatibility.py
"""
Capa de compatibilidad para mantener endpoints existentes
funcionando mientras se migra al nuevo sistema modular.

"""

from flask import Blueprint, request, jsonify, current_app
from utils.powershell_client import send_command_to_powershell, send_command_to_machine
import logging
from modules.auth.decorators import require_role

logger = logging.getLogger(__name__)

# Blueprint para mantener compatibilidad con endpoints existentes
compat_bp = Blueprint('compatibility', __name__)


def _resolve_machine(machine_id):
    """Devuelve (ip, port) para una machine_id dada, o (None, None) si no aplica."""
    if not machine_id:
        return None, None
    try:
        from database.models import Machine
        machine = Machine.query.get(int(machine_id))
        if machine:
            return machine.ip, machine.port
    except Exception as e:
        logger.warning(f"No se pudo resolver machine_id={machine_id}: {e}")
    return None, None


def _send(command, machine_id=None):
    """Envía un comando a la máquina indicada o a la máquina local por defecto."""
    ip, port = _resolve_machine(machine_id)
    if ip and port:
        return send_command_to_machine(command, ip, port)
    return send_command_to_powershell(command)


@compat_bp.route('/procesos', methods=['GET'])
def procesos_legacy():
    """
    Endpoint original para compatibilidad con el frontend actual
    Mantiene la misma interfaz que el sistema original
    """
    action = request.args.get('action')
    comando = request.args.get('comando')
    pid = request.args.get('pid')
    machine_id = request.args.get('machine_id')

    logger.debug(f"Request a /procesos: action={action}, comando={comando}, pid={pid}, machine_id={machine_id}")

    # Mapear acciones a comandos de PowerShell
    if action == 'listar' or action == 'process':
        command = 'process'
    elif action == 'cpu':
        command = 'cpu'
    elif action == 'memory':
        command = 'memory'
    elif action == 'backup':
        command = 'backup'
    elif action == 'compress':
        command = 'compress'
    elif action == 'log':
        count = request.args.get('count', '').strip()
        command = f'log {count}' if count.isdigit() else 'log'
    elif action == 'network':
        command = 'network'
    elif action == 'permisos':
        command = 'permisos'
    elif action == 'servicios':
        count = request.args.get('count', '').strip()
        if count == 'all':
            command = 'servicios all'
        elif count.isdigit():
            command = f'servicios {count}'
        else:
            command = 'servicios'
    elif action == 'restart':
        command = 'restart'
    elif action == 'iniciar' and comando:
        command = f'iniciar {comando}'
    elif action == 'matar' and pid:
        command = f'matar {pid}'
    else:
        logger.warning(f"Acción inválida o faltan parámetros: action={action}, comando={comando}, pid={pid}")
        return jsonify({"error": "Acción no válida o faltan parámetros"}), 400

    # Ejecutar comando y devolver respuesta en formato original
    output = _send(command, machine_id)
    return jsonify({"output": output})

@compat_bp.route('/api/command', methods=['POST'])
@require_role('superadmin', 'admin')
def execute_command_legacy():
    """
    Endpoint para ejecutar comandos arbitrarios (compatibilidad)
    Mantiene la misma interfaz que el sistema original
    """
    data = request.json

    if not data or 'command' not in data:
        return jsonify({"error": "No se proporcionó comando"}), 400

    command = data['command']
    machine_id = data.get('machine_id')
    
    # Lista de comandos permitidos para seguridad
    allowed_commands = [
        'cpu', 'memory', 'process', 'backup', 'compress', 'log', 
        'disk', 'network', 'permisos', 'servicios', 'restart',
        'list_disks', 'list_partitions'
    ]
    
    # Verificar si es un comando permitido o tiene un prefijo permitido
    is_allowed = any([
        command in allowed_commands,
        command.startswith('iniciar '),
        command.startswith('matar '),
        command.startswith('disk_detail '),
        command.startswith('check_disk '),
        command.startswith('defrag_disk '),
        command.startswith('smart_test '),
        command.startswith('clone_disk '),
        command.startswith('convert_disk '),
        command.startswith('mount_image '),
        command.startswith('create_partition '),
        command.startswith('format_partition '),
        command.startswith('delete_partition '),
        command.startswith('resize_partition ')
    ])
    
    if not is_allowed:
        logger.warning(f"Comando no permitido: {command}")
        return jsonify({"error": "Comando no permitido"}), 403

    output = _send(command, machine_id)
    return jsonify({"output": output})

@compat_bp.route('/api/system', methods=['GET'])
def get_system_data_legacy():
    """
    Endpoint de compatibilidad para datos del sistema.
    Si se pasa machine_id, obtiene datos en tiempo real de esa máquina (sin fallback a localhost).
    Si no, usa el caché de la máquina local.
    """
    machine_id = request.args.get('machine_id')
    logger.debug(f"/api/system llamado con machine_id={machine_id!r}")

    if machine_id:
        try:
            from database.models import Machine
            from utils.background_tasks import parse_cpu_output, parse_memory_output, parse_disk_output

            machine = Machine.query.get(int(machine_id))
            if not machine:
                return jsonify({"error": f"Máquina {machine_id} no encontrada"}), 404

            logger.debug(f"Consultando máquina '{machine.name}' en {machine.ip}:{machine.port}")

            cpu_raw  = send_command_to_machine('cpu',    machine.ip, machine.port)
            mem_raw  = send_command_to_machine('memory', machine.ip, machine.port)
            disk_raw = send_command_to_machine('disk',   machine.ip, machine.port)

            logger.debug(f"cpu_raw={cpu_raw!r}  mem_raw={mem_raw!r}  disk_raw={disk_raw!r}")

            cpu_val  = parse_cpu_output(cpu_raw)
            mem_val  = parse_memory_output(mem_raw)
            disk_val = parse_disk_output(disk_raw)

            reachable = not any(
                err in cpu_raw for err in ["No se pudo conectar", "Error conectando"]
            )

            return jsonify({
                "cpu":       {"value": cpu_val,  "history": [cpu_val]  * 15},
                "memory":    {"value": mem_val,  "history": [mem_val]  * 15},
                "disk":      disk_val,
                "processes": [],
                "machine":   {"id": machine.id, "name": machine.name,
                               "ip": machine.ip, "reachable": reachable},
            })
        except Exception as e:
            logger.error(f"Error obteniendo datos de máquina {machine_id}: {e}", exc_info=True)
            return jsonify({"error": f"Error al obtener datos: {e}"}), 500

    try:
        cache_manager = current_app.cache_manager
        system_data = cache_manager.get_all_system_data()
        return jsonify(system_data)
    except Exception as e:
        logger.error(f"Error en endpoint de compatibilidad /api/system: {str(e)}")
        return jsonify({"error": "Error interno del servidor"}), 500

@compat_bp.route('/api/cpu', methods=['GET'])
def get_cpu_data_legacy():
    """Endpoint de compatibilidad para datos de CPU"""
    try:
        cache_manager = current_app.cache_manager
        cpu_data = cache_manager.get_cache_data("cpu")
        return jsonify(cpu_data)
    except Exception as e:
        logger.error(f"Error en endpoint de compatibilidad /api/cpu: {str(e)}")
        return jsonify({"error": "Error interno del servidor"}), 500

@compat_bp.route('/api/memory', methods=['GET'])
def get_memory_data_legacy():
    """Endpoint de compatibilidad para datos de memoria"""
    try:
        cache_manager = current_app.cache_manager
        memory_data = cache_manager.get_cache_data("memory")
        return jsonify(memory_data)
    except Exception as e:
        logger.error(f"Error en endpoint de compatibilidad /api/memory: {str(e)}")
        return jsonify({"error": "Error interno del servidor"}), 500

@compat_bp.route('/api/processes', methods=['GET'])
def get_processes_data_legacy():
    """Endpoint de compatibilidad para datos de procesos"""
    try:
        cache_manager = current_app.cache_manager
        processes_data = cache_manager.get_cache_data("processes")
        return jsonify(processes_data)
    except Exception as e:
        logger.error(f"Error en endpoint de compatibilidad /api/processes: {str(e)}")
        return jsonify({"error": "Error interno del servidor"}), 500

@compat_bp.route('/api/disk', methods=['GET'])
def get_disk_data_legacy():
    """Endpoint de compatibilidad para datos de disco"""
    try:
        cache_manager = current_app.cache_manager
        disk_data = cache_manager.get_cache_data("disk")
        return jsonify(disk_data)
    except Exception as e:
        logger.error(f"Error en endpoint de compatibilidad /api/disk: {str(e)}")
        return jsonify({"error": "Error interno del servidor"}), 500

# Endpoints heredados para herramientas de disco
@compat_bp.route('/api/disk_tool', methods=['POST'])
@require_role('superadmin', 'admin')
def execute_disk_tool_legacy():
    """Endpoint heredado para herramientas de disco"""
    data = request.json
    
    if not data:
        return jsonify({"error": "No se proporcionaron datos"}), 400
    
    tool = data.get('tool')
    machine_id = data.get('machine_id')

    if not tool:
        return jsonify({"error": "No se proporcionó herramienta"}), 400
    
    # Construir el comando para PowerShell según la herramienta
    command = None
    
    if tool == 'check':
        disk_id = data.get('disk_id')
        if not disk_id:
            return jsonify({"error": "No se proporcionó ID de disco"}), 400
        command = f'check_disk {disk_id}'
    
    elif tool == 'defrag':
        disk_id = data.get('disk_id')
        if not disk_id:
            return jsonify({"error": "No se proporcionó ID de disco"}), 400
        command = f'defrag_disk {disk_id}'
    
    elif tool == 'smart':
        disk_id = data.get('disk_id')
        if not disk_id:
            return jsonify({"error": "No se proporcionó ID de disco"}), 400
        command = f'smart_test {disk_id}'
    
    elif tool == 'clone':
        source_disk_id = data.get('source_disk_id')
        target_disk_id = data.get('target_disk_id')
        if not source_disk_id or not target_disk_id:
            return jsonify({"error": "No se proporcionaron los IDs de disco origen y destino"}), 400
        command = f'clone_disk {source_disk_id} {target_disk_id}'
    
    elif tool == 'convert':
        disk_id = data.get('disk_id')
        disk_type = data.get('type')
        if not disk_id or not disk_type:
            return jsonify({"error": "No se proporcionó ID de disco o tipo de conversión"}), 400
        command = f'convert_disk {disk_id} {disk_type}'
    
    elif tool == 'mount':
        image_path = data.get('image_path')
        if not image_path:
            return jsonify({"error": "No se proporcionó ruta de imagen"}), 400
        command = f'mount_image {image_path}'
    
    else:
        return jsonify({"error": f"Herramienta no válida: {tool}"}), 400
    
    output = _send(command, machine_id)
    return jsonify({"output": output})


@compat_bp.route('/api/partition_operation', methods=['POST'])
@require_role('superadmin', 'admin')
def execute_partition_operation_legacy():
    """Endpoint heredado para operaciones en particiones"""
    data = request.json
    
    if not data:
        return jsonify({"error": "No se proporcionaron datos"}), 400
    
    operation = data.get('operation')
    machine_id = data.get('machine_id')

    if not operation:
        return jsonify({"error": "No se proporcionó operación"}), 400
    
    # Construir el comando para PowerShell según la operación
    command = None
    
    if operation == 'create':
        disk_id = data.get('disk_id')
        size = data.get('size')
        filesystem = data.get('filesystem')
        label = data.get('label', '')
        
        if not disk_id or not size or not filesystem:
            return jsonify({"error": "Faltan parámetros requeridos (disk_id, size, filesystem)"}), 400
        
        command = f'create_partition {disk_id} {size} {filesystem} {label}'
    
    elif operation == 'format':
        partition_id = data.get('partition_id')
        filesystem = data.get('filesystem')
        label = data.get('label', '')
        
        if not partition_id or not filesystem:
            return jsonify({"error": "Faltan parámetros requeridos (partition_id, filesystem)"}), 400
        
        command = f'format_partition {partition_id} {filesystem} {label}'
    
    elif operation == 'delete':
        partition_id = data.get('partition_id')
        
        if not partition_id:
            return jsonify({"error": "No se proporcionó ID de partición"}), 400
        
        command = f'delete_partition {partition_id}'
    
    else:
        return jsonify({"error": f"Operación no válida: {operation}"}), 400
    
    output = _send(command, machine_id)
    return jsonify({"output": output})