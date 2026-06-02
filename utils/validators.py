import re

# ── Patrones base ──────────────────────────────────────────────────────────────

_WINDOWS_PATH_RE = re.compile(r'^[A-Za-z]:\\[\w\s\-\.\\/]+$')
_SAFE_NAME_RE = re.compile(r'^[\w\-]{1,64}$')
_DISK_ID_RE = re.compile(r'^disk\d{1,3}$', re.IGNORECASE)
_PARTITION_ID_RE = re.compile(r'^\d{1,3}$')
_SCHEDULE_TIME_RE = re.compile(r'^\d{2}:\d{2}$')
_ADAPTER_NAME_RE = re.compile(r'^[\w\s\-\.\(\)]{1,64}$')  # incluye paréntesis (ej: vEthernet (WSL))

# Direccion IPv4 estricta
_IPV4_RE = re.compile(r'^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$')
# Hostname / FQDN (RFC 1123)
_HOSTNAME_RE = re.compile(
    r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)'
    r'(?:\.(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?))*$'
)

# ── Allowlists ─────────────────────────────────────────────────────────────────

ALLOWED_BACKUP_TYPES = {'full', 'incremental', 'differential'}
ALLOWED_SCHEDULE_TYPES = {'daily', 'weekly', 'monthly'}
ALLOWED_JOB_SCHEDULES = {'manual', 'daily', 'weekly', 'monthly'}
ALLOWED_COMPRESS_LEVELS = {'low', 'normal', 'high', 'maximum'}
ALLOWED_FILESYSTEMS = {'NTFS', 'FAT32', 'exFAT', 'ReFS'}
ALLOWED_DISK_TYPES = {'MBR', 'GPT'}
ALLOWED_DESTINATION_TYPES = {'local', 'network', 'cloud', 'ftp'}

# ── Funciones de validación ────────────────────────────────────────────────────


def validate_windows_path(path, field_name: str) -> str:
    path = (path or '').strip()
    if not path:
        raise ValueError(f"{field_name}: la ruta es obligatoria")
    if '..' in path:
        raise ValueError(f"{field_name}: path traversal no permitido")
    if not _WINDOWS_PATH_RE.match(path):
        raise ValueError(
            f"{field_name}: ruta Windows no válida "
            "(debe ser ruta absoluta, ej: C:\\carpeta\\subcarpeta)"
        )
    return path


def validate_safe_name(name, field_name: str) -> str:
    name = (name or '').strip()
    if not name or not _SAFE_NAME_RE.match(name):
        raise ValueError(
            f"{field_name}: solo se permiten letras, números, guiones y "
            "subrayados (máx. 64 caracteres)"
        )
    return name


def validate_enum(value, allowed: set, field_name: str) -> str:
    value = (value or '').strip()
    if value not in allowed:
        raise ValueError(
            f"{field_name}: valor no permitido '{value}'. "
            f"Opciones válidas: {sorted(allowed)}"
        )
    return value


def validate_disk_id(value) -> str:
    value = str(value or '').strip()
    if not _DISK_ID_RE.match(value):
        raise ValueError(
            f"disk_id no válido '{value}': formato esperado 'disk0', 'disk1', etc."
        )
    return value.lower()


def validate_id(value, field_name: str = 'id') -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name}: debe ser un entero")
    if n <= 0:
        raise ValueError(f"{field_name}: debe ser un entero positivo")
    return n


_DRIVE_LETTER_RE = re.compile(r'^[A-Za-z]:?$')


def validate_drive_letter(value) -> str:
    """Acepta 'D', 'd', 'D:', 'd:'. Devuelve la letra mayúscula sin ':'.

    Rechaza A/B/C (reservadas) y cualquier otra cosa.
    """
    if value is None or value == '':
        return ''
    s = str(value).strip().rstrip(':').upper()
    if not _DRIVE_LETTER_RE.match(str(value).strip()):
        raise ValueError(f"letra de unidad no válida '{value}' (debe ser una letra A-Z)")
    if s in ('A', 'B', 'C'):
        raise ValueError(f"la letra '{s}' está reservada (A/B disquetes, C sistema)")
    return s


def validate_partition_id(value) -> str:
    value = str(value or '').strip()
    if not _PARTITION_ID_RE.match(value):
        raise ValueError(
            f"partition_id no válido '{value}': debe ser un número (ej: 1, 2)"
        )
    return value


def validate_numeric(value, field_name: str, min_val: float = 0,
                     max_val: float = None) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name}: debe ser un número")
    if n < min_val:
        raise ValueError(f"{field_name}: debe ser >= {min_val}")
    if max_val is not None and n > max_val:
        raise ValueError(f"{field_name}: debe ser <= {max_val}")
    return n


def validate_schedule_time(value) -> str:
    value = (value or '').strip()
    if not _SCHEDULE_TIME_RE.match(value):
        raise ValueError("schedule_time: formato HH:MM requerido (ej: 02:00)")
    h, m = int(value.split(':')[0]), int(value.split(':')[1])
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError("schedule_time: hora o minuto fuera de rango")
    return value


def validate_network_target(value) -> str:
    value = (value or '').strip()
    if not value:
        return '8.8.8.8'
    if _IPV4_RE.match(value) or _HOSTNAME_RE.match(value):
        return value
    raise ValueError(
        f"Destino de red no válido '{value}': "
        "solo se aceptan direcciones IP o nombres de host"
    )


def validate_adapter_name(value) -> str:
    value = (value or '').strip()
    if not value or not _ADAPTER_NAME_RE.match(value):
        raise ValueError(
            "Nombre de adaptador no válido: solo letras, números, "
            "espacios, guiones y puntos (máx. 64 caracteres)"
        )
    return value


def validate_password_strength(password: str) -> str:
    if not password or len(password) < 12:
        raise ValueError("La contraseña debe tener al menos 12 caracteres")
    if not re.search(r'[A-Z]', password):
        raise ValueError("La contraseña debe contener al menos una letra mayúscula")
    if not re.search(r'[a-z]', password):
        raise ValueError("La contraseña debe contener al menos una letra minúscula")
    if not re.search(r'\d', password):
        raise ValueError("La contraseña debe contener al menos un número")
    if not re.search(r'[^A-Za-z0-9]', password):
        raise ValueError("La contraseña debe contener al menos un carácter especial")
    return password
