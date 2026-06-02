# utils/audit.py
import os
import logging
from logging.handlers import RotatingFileHandler

# Ruta absoluta: audit.log se guarda en <proyecto>/logs/ — directorio que en
# Docker está bind-montado al host, por lo que sobrevive a docker compose
# down/up (a diferencia de la raíz del contenedor, que se destruye).
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_LOGS_DIR = os.path.join(_PROJECT_ROOT, 'logs')
try:
    os.makedirs(_LOGS_DIR, exist_ok=True)
except Exception:
    pass
# Compatibilidad: si existe un audit.log antiguo en la raíz pero no en logs/,
# lo movemos para no perder histórico.
_LEGACY_PATH = os.path.join(_PROJECT_ROOT, 'audit.log')
_LOG_PATH = os.path.join(_LOGS_DIR, 'audit.log')
if os.path.exists(_LEGACY_PATH) and not os.path.exists(_LOG_PATH):
    try:
        os.rename(_LEGACY_PATH, _LOG_PATH)
    except Exception:
        pass

_handler = RotatingFileHandler(_LOG_PATH, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8')
_handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))

_audit = logging.getLogger('audit')
_audit.setLevel(logging.INFO)
if not _audit.handlers:
    _audit.addHandler(_handler)
_audit.propagate = False  # no contaminar app.log con eventos de auditoría


AUDIT_LOG_PATH = _LOG_PATH


def _machine_label_from_id(machine_id):
    """Convierte un machine_id (int o str) en una etiqueta para audit.log."""
    if not machine_id:
        return None
    try:
        from database.models import Machine
        m = Machine.query.get(int(machine_id))
        if m:
            return (m.name or f'id:{machine_id}').replace(' ', '_')
    except Exception:
        pass
    return f'id:{machine_id}'


def _resolve_machine_label():
    """Devuelve el nombre de la máquina activa (vía machine_id) o 'local'.

    Lee machine_id desde query string, JSON body o form. Si la máquina existe en
    la BD usa su nombre; si no, devuelve 'id:<n>'. Si no hay request o BD,
    'local'. Sin espacios para no romper el formato de log.
    """
    try:
        from flask import request, has_request_context
        if not has_request_context():
            return 'local'
        machine_id = request.args.get('machine_id')
        if not machine_id:
            try:
                data = request.get_json(silent=True) or {}
                machine_id = data.get('machine_id')
            except Exception:
                machine_id = None
        if not machine_id:
            machine_id = request.form.get('machine_id') if request.form else None
        label = _machine_label_from_id(machine_id)
        return label or 'local'
    except Exception:
        return 'local'


def log_action(action: str, resource: str, detail: str = '', machine_id=None):
    """Registra una acción en audit.log.

    Formato:
        <timestamp> user=<u> uid=<id> ip=<ip> machine=<m> action=<a> resource=<r> [detail="..."]

    uid permite resolver el username actual aunque haya cambiado desde que se
    escribió la línea. Ausente en acciones anónimas o de sistema.

    Si `machine_id` se pasa explícitamente, se usa esa máquina (útil cuando la
    acción se ejecuta fuera del request, ej. en un thread de fondo, o cuando la
    máquina viene determinada por el recurso y no por el request).

    Si no se pasa, se intenta resolver desde el request actual (query/body/form).
    """
    try:
        from flask_login import current_user
        from flask import request, has_request_context
        if has_request_context():
            if current_user.is_authenticated:
                user = current_user.username
                uid = current_user.id
            else:
                user = 'anonymous'
                uid = None
            ip = request.remote_addr or '-'
        else:
            user = 'system'
            uid = None
            ip = '-'
        if machine_id is not None:
            machine = _machine_label_from_id(machine_id) or 'local'
        else:
            machine = _resolve_machine_label()
    except RuntimeError:
        user = 'system'
        uid = None
        ip = '-'
        machine = _machine_label_from_id(machine_id) or 'local' if machine_id is not None else 'local'

    uid_part = f' uid={uid}' if uid is not None else ''
    detail_part = f' detail="{detail}"' if detail else ''
    _audit.info(
        f'user={user}{uid_part} ip={ip} machine={machine} '
        f'action={action} resource={resource}{detail_part}'
    )
