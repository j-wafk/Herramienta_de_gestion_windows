# config.py
import os


def _require_env(var: str, hint: str = '') -> str:
    val = os.getenv(var, '').strip()
    if not val:
        msg = f"La variable de entorno '{var}' es obligatoria y no está configurada."
        if hint:
            msg += f" {hint}"
        raise RuntimeError(msg)
    return val


class Config:
    # Configuración de servidor PowerShell
    POWERSHELL_SERVER = os.getenv('POWERSHELL_SERVER', '127.0.0.1')
    POWERSHELL_PORT = int(os.getenv('POWERSHELL_PORT', 12345))
    # 3 s: un PS server vivo contesta en <100 ms; tras 3 s casi seguro está caído.
    # Bajar este número acelera mucho la carga de páginas cuando una máquina
    # remota está apagada. Subirlo solo si tienes redes lentas/saturadas.
    SOCKET_TIMEOUT = int(os.getenv('SOCKET_TIMEOUT', 3))

    # Configuración de caché
    CACHE_TIME = int(os.getenv('CACHE_TIME', 3))

    # Configuración de Flask
    SECRET_KEY = _require_env(
        'SECRET_KEY',
        "Genera una con: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
    DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

    # Configuración de backup
    BACKUP_DEFAULT_PATH = os.getenv('BACKUP_PATH', 'C:\\Backups')

    # Configuración de particiones
    PARTITION_OPERATIONS_ALLOWED = os.getenv('PARTITION_OPS', 'True').lower() == 'true'

    # Base de datos (PostgreSQL)
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://gestion:gestion@localhost:5432/gestion_db')
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Retención de métricas históricas (días)
    METRICS_RETENTION_DAYS = int(os.getenv('METRICS_RETENTION_DAYS', 30))

    # Cifrado de campos sensibles en BD (email, nombre, cuerpo de correos)
    FIELD_ENCRYPTION_KEY = _require_env(
        'FIELD_ENCRYPTION_KEY',
        "Clave de cifrado de columnas sensibles. "
        "Genera una con: python -c \"import secrets; print(secrets.token_hex(32))\""
    )

    # Autenticación — bootstrap superadmin
    ADMIN_USER     = os.getenv('ADMIN_USER', 'admin')
    ADMIN_PASSWORD = _require_env(
        'ADMIN_PASSWORD',
        "Contraseña para el superadmin inicial. Mínimo 12 caracteres."
    )

    # ──────────────── SMTP / Notificaciones por email ─────────────────
    # MAIL_ENABLED=false desactiva por completo el envío (no-op en send_email).
    # En dev sin MailHog déjalo en false para que la app no intente conectar.
    MAIL_ENABLED   = os.getenv('MAIL_ENABLED', 'false').lower() == 'true'
    SMTP_HOST      = os.getenv('SMTP_HOST', 'localhost')
    SMTP_PORT      = int(os.getenv('SMTP_PORT', 25))
    SMTP_USER      = os.getenv('SMTP_USER', '')
    SMTP_PASSWORD  = os.getenv('SMTP_PASSWORD', '')
    SMTP_USE_TLS   = os.getenv('SMTP_USE_TLS', 'false').lower() == 'true'   # STARTTLS (587)
    SMTP_USE_SSL   = os.getenv('SMTP_USE_SSL', 'false').lower() == 'true'   # SMTPS (465)
    SMTP_TIMEOUT   = int(os.getenv('SMTP_TIMEOUT', 10))
    MAIL_FROM      = os.getenv('MAIL_FROM', 'alertas@gestion.local')
    MAIL_FROM_NAME = os.getenv('MAIL_FROM_NAME', 'Control Remoto Windows')