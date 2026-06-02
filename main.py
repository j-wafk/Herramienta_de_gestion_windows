# main.py
import os
import logging
import threading

from datetime import timedelta, datetime

from flask import Flask, render_template, redirect, url_for, jsonify, request, session
from flask_cors import CORS
from flask_login import LoginManager, current_user, logout_user
from flask_talisman import Talisman
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from database import db, migrate
from extensions import limiter, csrf
from utils.cache_manager import CacheManager
from utils.powershell_client import health_check_powershell
from utils.background_tasks import background_data_refresh, get_background_status

# Blueprints de cada módulo
from modules.rendimiento.routes import rendimiento_bp
from modules.particiones.routes import particiones_bp
from modules.backup.routes import backup_bp
from modules.machines.routes import machines_bp
from modules.hardware.routes import hardware_bp
from modules.red.routes import red_bp
from modules.auth.routes import auth_bp
from modules.monitorizacion import monitorizacion_bp
from modules.monitorizacion.poller import start_poller as start_monit_poller
from modules.notifications import notifications_bp
from utils.mailer_worker import start_worker as start_mailer_worker

# Blueprint de compatibilidad
from compatibility import compat_bp
from modules.export.routes import export_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Confiar en los headers X-Forwarded-Proto / X-Forwarded-For de nginx
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_for=1)

    # Cookies de sesión seguras
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = not Config.DEBUG  # True en producción
    app.config['REMEMBER_COOKIE_SECURE'] = not Config.DEBUG
    app.config['REMEMBER_COOKIE_HTTPONLY'] = True

    # Sesión permanente con expiración de 8 horas; el before_request añade
    # inactividad máxima de 30 minutos para mayor seguridad.
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)

    # Configuración CSRF
    app.config['WTF_CSRF_TIME_LIMIT'] = 3600   # 1 hora
    app.config['WTF_CSRF_SSL_STRICT'] = not Config.DEBUG  # En producción, tokens solo de HTTPS

    # Configurar logging — app.log también vive en logs/ para que el bind
    # mount de Docker lo persista a través de down/up.
    _project_root = os.path.abspath(os.path.dirname(__file__))
    _logs_dir = os.path.join(_project_root, 'logs')
    try:
        os.makedirs(_logs_dir, exist_ok=True)
    except Exception:
        pass
    _legacy_app_log = os.path.join(_project_root, 'app.log')
    _app_log = os.path.join(_logs_dir, 'app.log')
    if os.path.exists(_legacy_app_log) and not os.path.exists(_app_log):
        try:
            os.rename(_legacy_app_log, _app_log)
        except Exception:
            pass
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(_app_log),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)
    logger.info("Iniciando aplicación Flask...")

    # Cabeceras de seguridad HTTP
    # force_https=False en desarrollo; en producción poner True o usar variable de entorno.
    _csp = {
        'default-src': "'self'",
        'script-src':  ["'self'", "'unsafe-inline'"],   # inline JS en templates; reducir en el futuro
        'style-src':   ["'self'", "'unsafe-inline'"],   # inline CSS en templates
        'img-src':     ["'self'", 'data:'],
        'connect-src': "'self'",
        'font-src':    "'self'",
        'frame-ancestors': "'none'",
    }
    Talisman(
        app,
        force_https=os.getenv('FLASK_ENV') == 'production',
        strict_transport_security=True,
        strict_transport_security_max_age=31536000,
        strict_transport_security_include_subdomains=True,
        content_security_policy=_csp,
        x_content_type_options=True,
        frame_options='DENY',
        referrer_policy='strict-origin-when-cross-origin',
        session_cookie_secure=not Config.DEBUG,
        session_cookie_http_only=True,
        session_cookie_samesite='Lax',
        x_xss_protection=False,
    )

    # CORS restringido a orígenes conocidos
    _allowed_origins = os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:5000').split(',')
    CORS(app,
         origins=[o.strip() for o in _allowed_origins],
         supports_credentials=True,
         methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
         allow_headers=['Content-Type', 'X-CSRFToken'])

    # Inicializar extensiones
    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)
    csrf.init_app(app)

    # Eximir blueprints de API del CSRF de formulario.
    # La protección CSRF para API JSON la proveen: SameSite=Lax + CORS restringido
    # + el token X-CSRFToken incluido por csrf.js en todas las páginas autenticadas.
    for bp in (rendimiento_bp, particiones_bp, backup_bp, machines_bp,
               hardware_bp, red_bp, compat_bp, export_bp, monitorizacion_bp,
               notifications_bp):
        csrf.exempt(bp)

    # Inicializar Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    @login_manager.user_loader
    def load_user(user_id):
        from database.models import User
        return db.session.get(User, int(user_id))

    # Inicializar cache manager
    cache_manager = CacheManager()
    app.cache_manager = cache_manager

    # Registrar blueprints (auth primero)
    app.register_blueprint(auth_bp)
    app.register_blueprint(compat_bp)
    app.register_blueprint(rendimiento_bp, url_prefix='/api/rendimiento')
    app.register_blueprint(particiones_bp, url_prefix='/api/particiones')
    app.register_blueprint(backup_bp, url_prefix='/api/backup')
    app.register_blueprint(machines_bp, url_prefix='/api/machines')
    app.register_blueprint(hardware_bp, url_prefix='/api/hardware')
    app.register_blueprint(red_bp, url_prefix='/api/red')
    app.register_blueprint(export_bp, url_prefix='/api/export')
    app.register_blueprint(monitorizacion_bp, url_prefix='/api/monitorizacion')
    app.register_blueprint(notifications_bp,  url_prefix='/api/notifications')
    logger.info("Blueprints registrados")

    # Guard global: todas las rutas requieren autenticación salvo las abiertas
    _OPEN_ENDPOINTS = {
        'auth.login', 'auth.logout',
        'health_check',
        'static',
    }

    _INACTIVITY_SECONDS = 1800  # 30 minutos sin actividad → cierre de sesión

    @app.before_request
    def global_auth_check():
        if request.endpoint in _OPEN_ENDPOINTS:
            return
        if not current_user.is_authenticated:
            if request.path.startswith('/api/') or request.path.startswith('/auth/api/'):
                return jsonify({'error': 'No autenticado'}), 401
            return redirect(url_for('auth.login', next=request.path))

        # Comprobar inactividad (solo en peticiones no-estáticas con sesión activa)
        if request.endpoint != 'static':
            last_active_str = session.get('_last_active')
            now = datetime.utcnow()
            if last_active_str:
                try:
                    inactive_secs = (now - datetime.fromisoformat(last_active_str)).total_seconds()
                    if inactive_secs > _INACTIVITY_SECONDS:
                        logout_user()
                        session.clear()
                        if request.path.startswith('/api/') or request.path.startswith('/auth/api/'):
                            return jsonify({'error': 'Sesión expirada por inactividad'}), 401
                        return redirect(url_for('auth.login', next=request.path))
                except (ValueError, TypeError):
                    pass
            session['_last_active'] = now.isoformat()

    # Crear tablas y datos de arranque.
    # FLASK_SKIP_DB_INIT=true se usa durante 'flask db migrate' para que Alembic
    # pueda comparar los modelos contra una BD vacía y generar la migración inicial.
    _skip_db_init = os.getenv('FLASK_SKIP_DB_INIT', 'false').lower() == 'true'
    with app.app_context():
        from database.models import (  # noqa: F401 — registrar tablas
            HardwareSnapshot,
            BackupDestination, BackupJob, BackupRun,
            MonitoredService, ServiceCheck,
            EmailQueue, NotificationPreference,
        )
        if not _skip_db_init:
            from flask_migrate import upgrade as _db_upgrade
            _db_upgrade()
            _migrate_users_profile_columns()
            _migrate_backup_runs_columns()
            _migrate_monitoring_columns()
            _migrate_encryption_columns()
            _ensure_local_machine()
            _ensure_superadmin()
            logger.info("Base de datos inicializada")

    # Arrancar hilo de background
    background_thread = threading.Thread(
        target=background_data_refresh,
        args=(cache_manager, app),
        daemon=True,
        name='background-refresh',
    )
    background_thread.start()
    logger.info("Hilo de actualización en segundo plano iniciado")

    # Arrancar poller de servicios monitorizados (TCP/UDP/HTTPS a IP:puerto)
    try:
        start_monit_poller(app)
    except Exception as e:
        logger.warning(f"No se pudo iniciar el poller de monitorización: {e}")

    # Arrancar worker de envío de emails (procesa EmailQueue con backoff)
    try:
        start_mailer_worker(app)
    except Exception as e:
        logger.warning(f"No se pudo iniciar el worker de mailer: {e}")

    # Rutas principales
    @app.route('/')
    def index():
        return render_template('vista_general.html')

    @app.route('/rendimiento')
    def rendimiento_page():
        return render_template('index.html')

    @app.route('/particiones')
    def particiones_page():
        return render_template('particiones.html')

    @app.route('/backup')
    def backup_page():
        return render_template('backup.html')

    @app.route('/hardware')
    def hardware_page():
        return render_template('hardware.html')

    @app.route('/red')
    def red_page():
        return render_template('red.html')

    @app.route('/monitorizacion')
    def monitorizacion_page():
        return render_template('monitorizacion.html')

    @app.route('/health')
    def health_check():
        return jsonify({"status": "ok", "message": "Servidor Flask funcionando correctamente"})

    @app.route('/health/powershell')
    def health_check_ps():
        """Verifica conectividad con el servidor PowerShell (requiere autenticación)."""
        return health_check_powershell()

    @app.route('/health/background')
    def health_check_background():
        """Estado del hilo de refresco de métricas.

        Devuelve 200 si el hilo ha completado un ciclo recientemente,
        503 si está parado o ha quedado obsoleto. Requiere autenticación
        (el endpoint queda bajo el guard global before_request).
        """
        status = get_background_status()
        http_code = 200 if status['healthy'] else 503
        return jsonify(status), http_code

    @app.errorhandler(404)
    def not_found(error):
        logger.warning(f"404: {request.path}")
        return {'error': 'Endpoint no encontrado'}, 404

    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"500: {error}")
        return {'error': 'Error interno del servidor'}, 500

    @app.errorhandler(403)
    def forbidden(error):
        return jsonify({'error': 'Acceso denegado'}), 403

    @app.errorhandler(429)
    def rate_limit_exceeded(error):
        is_login = (request.endpoint == 'auth.login'
                    or request.path.rstrip('/') == '/auth/login')

        # En login, bloquea la cuenta 10 min para que el rate-limit por IP no
        # se pueda sortear cambiando de IP, y avísala como cuenta bloqueada.
        if is_login and request.method == 'POST':
            from database.models import User
            from utils.audit import log_action
            username = (request.form.get('username') or '').strip()
            if username:
                try:
                    user = User.query.filter_by(username=username).first()
                    if user is not None:
                        user.locked_until = datetime.utcnow() + timedelta(minutes=10)
                        user.failed_attempts = 0
                        db.session.commit()
                        log_action('login_blocked_ratelimit', f'user:{username}',
                                   'lock=10min')
                except Exception:
                    db.session.rollback()

        msg = ('Cuenta bloqueada por demasiados intentos. '
               'Inténtalo de nuevo en 10 minutos o pide a un administrador que la desbloquee.') \
            if is_login else \
            'Demasiados intentos. Espera un momento antes de volver a intentarlo.'

        if is_login:
            return render_template('auth/login.html', error=msg), 429
        return jsonify({'error': msg}), 429

    return app


def _migrate_users_profile_columns():
    """Añade las columnas de perfil a la tabla users si no existen (migración idempotente)."""
    from sqlalchemy import text
    log = logging.getLogger(__name__)
    cols = [
        ("email",               "VARCHAR(120)"),
        ("full_name",           "VARCHAR(120)"),
        ("language",            "VARCHAR(5)  NOT NULL DEFAULT 'es'"),
        ("theme",               "VARCHAR(10) NOT NULL DEFAULT 'light'"),
        ("avatar_color",        "VARCHAR(7)  NOT NULL DEFAULT '#0A67DC'"),
        ("email_notifications", "BOOLEAN     NOT NULL DEFAULT FALSE"),
        ("updated_at",          "TIMESTAMP"),
        ("failed_attempts",     "INTEGER     NOT NULL DEFAULT 0"),
        ("locked_until",        "TIMESTAMP"),
    ]
    with db.engine.connect() as conn:
        for col, col_type in cols:
            try:
                conn.execute(text(
                    f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {col_type}"
                ))
                conn.commit()
            except Exception as e:
                conn.rollback()
                log.warning(f"Migración columna '{col}' omitida: {e}")
    log.info("Migración de columnas de perfil completada")


def _migrate_backup_runs_columns():
    """Añade columnas snapshot a backup_runs si no existen (idempotente)."""
    from sqlalchemy import text
    log = logging.getLogger(__name__)
    cols = [
        ("job_name_snapshot",    "VARCHAR(120)"),
        ("backup_type_snapshot", "VARCHAR(20)"),
    ]
    with db.engine.connect() as conn:
        for col, col_type in cols:
            try:
                conn.execute(text(
                    f"ALTER TABLE backup_runs ADD COLUMN IF NOT EXISTS {col} {col_type}"
                ))
                conn.commit()
            except Exception as e:
                conn.rollback()
                log.warning(f"Migración backup_runs columna '{col}' omitida: {e}")
    log.info("Migración de columnas de backup_runs completada")


def _migrate_monitoring_columns():
    """Añade `description` a la tabla machines si no existe (idempotente)."""
    from sqlalchemy import text
    log = logging.getLogger(__name__)
    with db.engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE machines ADD COLUMN IF NOT EXISTS description VARCHAR(200)"))
            conn.commit()
        except Exception as e:
            conn.rollback()
            log.warning(f"Migración machines.description omitida: {e}")
    log.info("Migración de columnas de monitorización completada")


def _migrate_encryption_columns():
    """Migración idempotente para cifrado de columnas sensibles.

    Pasos:
      1. Añade users.email_hash (VARCHAR 64) si no existe.
      2. Intenta borrar el antiguo UNIQUE constraint de users.email (ya no es
         útil porque el valor almacenado es ciphertext no-determinista).
      3. Cifra con Fernet cualquier email en texto plano y rellena email_hash.
      4. Cifra cuerpos de email_queue en texto plano (to_addr, body_html, body_text).
    """
    from sqlalchemy import text
    from utils.encryption import _get_fernet, compute_search_hash
    log = logging.getLogger(__name__)
    _PREFIX = 'gAAAAA'  # prefijo fijo de todos los tokens Fernet

    with db.engine.connect() as conn:
        # 1. Columna email_hash
        try:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_hash VARCHAR(64)"
            ))
            conn.commit()
        except Exception as e:
            conn.rollback()
            log.warning("Migración users.email_hash: %s", e)

        # 2. Eliminar antiguo UNIQUE en email (PostgreSQL lo nombra users_email_key)
        try:
            conn.execute(text(
                "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_email_key"
            ))
            conn.commit()
        except Exception:
            conn.rollback()  # SQLite no soporta DROP CONSTRAINT; ignorar

        # 3. Cifrar emails en texto plano y rellenar email_hash
        try:
            rows = conn.execute(text(
                "SELECT id, email FROM users WHERE email IS NOT NULL"
            )).fetchall()
        except Exception as e:
            log.warning("No se pudo leer users para migración de cifrado: %s", e)
            rows = []

        fernet = _get_fernet()
        for row_id, raw_email in rows:
            if not raw_email:
                continue
            already_encrypted = raw_email.startswith(_PREFIX)
            if already_encrypted:
                try:
                    plaintext = fernet.decrypt(raw_email.encode('ascii')).decode('utf-8')
                except Exception:
                    continue  # ciphertext de otra clave — no tocar
                ciphertext = raw_email
            else:
                plaintext = raw_email
                ciphertext = fernet.encrypt(raw_email.encode('utf-8')).decode('ascii')

            h = compute_search_hash(plaintext)
            try:
                conn.execute(text(
                    "UPDATE users SET email = :e, email_hash = :h "
                    "WHERE id = :id AND (email_hash IS NULL OR email != :e)"
                ), {'e': ciphertext, 'h': h, 'id': row_id})
                conn.commit()
            except Exception as exc:
                conn.rollback()
                log.warning("Error cifrando email user id=%s: %s", row_id, exc)

        # 4. Cifrar campos de email_queue en texto plano
        for tbl_col in [('email_queue', 'to_addr'),
                        ('email_queue', 'body_html'),
                        ('email_queue', 'body_text')]:
            tbl, col = tbl_col
            try:
                eq_rows = conn.execute(text(
                    f"SELECT id, {col} FROM {tbl} WHERE {col} IS NOT NULL"  # noqa: S608
                )).fetchall()
            except Exception as e:
                log.warning("No se pudo leer %s.%s: %s", tbl, col, e)
                continue

            for eq_id, val in eq_rows:
                if not val or val.startswith(_PREFIX):
                    continue
                try:
                    enc = fernet.encrypt(val.encode('utf-8')).decode('ascii')
                    conn.execute(text(
                        f"UPDATE {tbl} SET {col} = :v WHERE id = :id"  # noqa: S608
                    ), {'v': enc, 'id': eq_id})
                    conn.commit()
                except Exception as exc:
                    conn.rollback()
                    log.warning("Error cifrando %s.%s id=%s: %s", tbl, col, eq_id, exc)

    log.info("Migración de cifrado de columnas completada")


def _ensure_local_machine():
    """Crea o actualiza la máquina local en la BD.

    Si ya existe un registro 'Local' con distinta IP (ej: 127.0.0.1 de una
    instalación anterior) lo actualiza a la IP configurada actualmente
    (ej: host.docker.internal cuando corre en Docker).
    """
    from database.models import Machine
    log = logging.getLogger(__name__)

    # Buscar con la configuración actual
    local = Machine.query.filter_by(
        ip=Config.POWERSHELL_SERVER,
        port=Config.POWERSHELL_PORT
    ).first()

    if not local:
        # Puede existir con IP obsoleta (ej: 127.0.0.1 → host.docker.internal)
        old = Machine.query.filter_by(name='Local', port=Config.POWERSHELL_PORT).first()
        if old:
            log.info(f"Actualizando IP de máquina local: {old.ip} → {Config.POWERSHELL_SERVER}")
            old.ip = Config.POWERSHELL_SERVER
            db.session.commit()
        else:
            local = Machine(
                name='Local',
                ip=Config.POWERSHELL_SERVER,
                port=Config.POWERSHELL_PORT,
                status='unknown',
            )
            db.session.add(local)
            db.session.commit()
            log.info(f"Máquina local creada en DB (id={local.id})")


def _ensure_superadmin():
    from database.models import User
    from utils.validators import validate_password_strength
    if User.query.count() == 0:
        try:
            validate_password_strength(Config.ADMIN_PASSWORD)
        except ValueError as e:
            raise RuntimeError(
                f"ADMIN_PASSWORD no cumple los requisitos de seguridad: {e}. "
                "Corrígela en el .env antes de arrancar."
            ) from e
        admin = User(
            username=Config.ADMIN_USER,
            role='superadmin',
            is_active=True,
        )
        admin.set_password(Config.ADMIN_PASSWORD)
        db.session.add(admin)
        db.session.commit()
        logging.getLogger(__name__).info(
            f"Superadmin bootstrap: usuario '{Config.ADMIN_USER}' creado"
        )


if __name__ == '__main__':
    app = create_app()
    logger = logging.getLogger(__name__)

    print("\n" + "="*50)
    print("SERVIDOR FLASK INICIADO")
    print("="*50)
    print("URL: http://localhost:5000")
    print("Login: http://localhost:5000/auth/login")
    print("Salud del servidor: http://localhost:5000/health")
    print("="*50 + "\n")

    app.run(host='0.0.0.0', port=5000, debug=Config.DEBUG, threaded=True)
