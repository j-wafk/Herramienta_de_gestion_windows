import json
from datetime import datetime
from database import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from utils.encryption import EncryptedString, EncryptedText


class Machine(db.Model):
    """Máquina gestionada remotamente."""
    __tablename__ = 'machines'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    ip = db.Column(db.String(45), nullable=False)
    port = db.Column(db.Integer, default=12345)
    status = db.Column(db.String(20), default='unknown')  # online / offline / unknown / warning
    description = db.Column(db.String(200), nullable=True)
    last_seen = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    metrics = db.relationship('SystemMetric', backref='machine', lazy='dynamic',
                              cascade='all, delete-orphan')
    services = db.relationship('Service', backref='machine', lazy='dynamic',
                               cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'ip': self.ip,
            'port': self.port,
            'status': self.status,
            'description': self.description,
            'last_seen': self.last_seen.isoformat() + 'Z' if self.last_seen else None,
            'created_at': self.created_at.isoformat() + 'Z',
        }


class SystemMetric(db.Model):
    """Snapshot de métricas de rendimiento de una máquina en un instante."""
    __tablename__ = 'system_metrics'

    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.Integer, db.ForeignKey('machines.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    cpu = db.Column(db.Float, nullable=True)
    memory = db.Column(db.Float, nullable=True)
    disk_used = db.Column(db.Float, nullable=True)
    disk_free = db.Column(db.Float, nullable=True)

    def to_dict(self):
        return {
            'timestamp': self.timestamp.isoformat() + 'Z',
            'cpu': self.cpu,
            'memory': self.memory,
            'disk_used': self.disk_used,
            'disk_free': self.disk_free,
        }


class HardwareSnapshot(db.Model):
    """Último snapshot de hardware de una máquina (un registro por máquina)."""
    __tablename__ = 'hardware_snapshots'

    id          = db.Column(db.Integer, primary_key=True)
    machine_id  = db.Column(db.Integer, db.ForeignKey('machines.id'), nullable=False, unique=True)
    timestamp   = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    system_json     = db.Column(db.Text, default='{}')
    cpu_json        = db.Column(db.Text, default='{}')
    memory_json     = db.Column(db.Text, default='{}')
    disks_json      = db.Column(db.Text, default='[]')
    gpu_json        = db.Column(db.Text, default='[]')
    motherboard_json= db.Column(db.Text, default='{}')
    devices_json    = db.Column(db.Text, default='[]')

    def to_dict(self):
        return {
            'timestamp':   self.timestamp.isoformat() + 'Z' if self.timestamp else None,
            'system':      json.loads(self.system_json      or '{}'),
            'cpu':         json.loads(self.cpu_json         or '{}'),
            'memory':      json.loads(self.memory_json      or '{}'),
            'disks':       json.loads(self.disks_json       or '[]'),
            'gpu':         json.loads(self.gpu_json         or '[]'),
            'motherboard': json.loads(self.motherboard_json or '{}'),
            'devices':     json.loads(self.devices_json     or '[]'),
        }


class Service(db.Model):
    """Servicio de Windows corriendo en una máquina."""
    __tablename__ = 'services'

    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.Integer, db.ForeignKey('machines.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    display_name = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(50), nullable=True)      # Running / Stopped / etc.
    start_type = db.Column(db.String(50), nullable=True)  # Auto / Manual / Disabled
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'machine_id': self.machine_id,
            'name': self.name,
            'display_name': self.display_name,
            'status': self.status,
            'start_type': self.start_type,
            'last_updated': self.last_updated.isoformat() + 'Z',
        }


class User(UserMixin, db.Model):
    """Usuario de la aplicación con rol para control de acceso."""
    __tablename__ = 'users'

    id                  = db.Column(db.Integer, primary_key=True)
    username            = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash       = db.Column(db.String(256), nullable=False)
    role                = db.Column(db.String(20), nullable=False, default='solo_lectura')
    is_active           = db.Column(db.Boolean, default=True, nullable=False)
    created_at          = db.Column(db.DateTime, default=datetime.utcnow)
    last_login          = db.Column(db.DateTime, nullable=True)
    # Perfil extendido — email y full_name se almacenan cifrados con Fernet.
    # email_hash es un HMAC-SHA256 del email (en minúsculas) usado para
    # comprobar unicidad y buscar sin descifrar la columna principal.
    email               = db.Column(EncryptedString(), nullable=True)
    email_hash          = db.Column(db.String(64), unique=True, nullable=True, index=True)
    full_name           = db.Column(EncryptedString(), nullable=True)
    language            = db.Column(db.String(5), nullable=False, default='es')
    theme               = db.Column(db.String(10), nullable=False, default='light')
    avatar_color        = db.Column(db.String(7), nullable=False, default='#0A67DC')
    email_notifications = db.Column(db.Boolean, nullable=False, default=False)
    updated_at          = db.Column(db.DateTime, nullable=True)
    failed_attempts     = db.Column(db.Integer,  nullable=False, default=0)
    locked_until        = db.Column(db.DateTime, nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id':                  self.id,
            'username':            self.username,
            'role':                self.role,
            'is_active':           self.is_active,
            'created_at':          self.created_at.isoformat() + 'Z' if self.created_at else None,
            'last_login':          self.last_login.isoformat() + 'Z' if self.last_login else None,
            'email':               self.email,
            'full_name':           self.full_name,
            'language':            self.language,
            'theme':               self.theme,
            'avatar_color':        self.avatar_color,
            'email_notifications': self.email_notifications,
            'updated_at':          self.updated_at.isoformat() + 'Z' if self.updated_at else None,
            'locked_until':        self.locked_until.isoformat() + 'Z' if self.locked_until else None,
            'is_locked':           bool(self.locked_until and self.locked_until > datetime.utcnow()),
        }


class BackupDestination(db.Model):
    """Destino donde se almacenan las copias de seguridad de una máquina."""
    __tablename__ = 'backup_destinations'

    id          = db.Column(db.Integer, primary_key=True)
    machine_id  = db.Column(db.Integer, db.ForeignKey('machines.id'), nullable=True, index=True)
    name        = db.Column(db.String(120), nullable=False)
    type        = db.Column(db.String(20), nullable=False, default='local')  # local|network|cloud|ftp
    path        = db.Column(db.String(500), nullable=False)
    status      = db.Column(db.String(20), nullable=False, default='unknown')  # online|offline|unknown
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    jobs = db.relationship('BackupJob', backref='destination', lazy='dynamic')

    def to_dict(self):
        return {
            'id':         self.id,
            'machine_id': self.machine_id,
            'name':       self.name,
            'type':       self.type,
            'path':       self.path,
            'status':     self.status,
            'supported':  self.type == 'local',
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
        }


class BackupJob(db.Model):
    """Trabajo configurado de copia de seguridad. Se ejecuta manual o programado."""
    __tablename__ = 'backup_jobs'

    id              = db.Column(db.Integer, primary_key=True)
    machine_id      = db.Column(db.Integer, db.ForeignKey('machines.id'), nullable=False, index=True)
    name            = db.Column(db.String(120), nullable=False)
    source_path     = db.Column(db.String(500), nullable=False)
    destination_id  = db.Column(db.Integer, db.ForeignKey('backup_destinations.id'), nullable=False)
    backup_type     = db.Column(db.String(20), nullable=False, default='full')  # full|incremental|differential
    schedule        = db.Column(db.String(20), nullable=False, default='manual')  # manual|daily|weekly|monthly
    schedule_time   = db.Column(db.String(5),  nullable=False, default='02:00')   # HH:MM
    compress        = db.Column(db.Boolean, nullable=False, default=True)
    verify_after    = db.Column(db.Boolean, nullable=False, default=True)
    encrypt         = db.Column(db.Boolean, nullable=False, default=False)  # reservado para versiones futuras
    notify          = db.Column(db.Boolean, nullable=False, default=False)
    enabled         = db.Column(db.Boolean, nullable=False, default=True)
    last_run_at     = db.Column(db.DateTime, nullable=True)
    next_run_at     = db.Column(db.DateTime, nullable=True)
    scheduled_task_name = db.Column(db.String(120), nullable=True)  # nombre real en Task Scheduler
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    # Sin cascade: al borrar un job sus runs deben quedar como histórico huérfano.
    runs = db.relationship('BackupRun', backref='job', lazy='dynamic',
                           passive_deletes=True)

    __table_args__ = (
        db.UniqueConstraint('machine_id', 'name', name='uq_backup_job_machine_name'),
    )

    def to_dict(self):
        return {
            'id':              self.id,
            'machine_id':      self.machine_id,
            'name':            self.name,
            'source_path':     self.source_path,
            'destination_id':  self.destination_id,
            'backup_type':     self.backup_type,
            'schedule':        self.schedule,
            'schedule_time':   self.schedule_time,
            'compress':        self.compress,
            'verify_after':    self.verify_after,
            'encrypt':         self.encrypt,
            'notify':          self.notify,
            'enabled':         self.enabled,
            'last_run_at':     self.last_run_at.isoformat() + 'Z' if self.last_run_at else None,
            'next_run_at':     self.next_run_at.isoformat() + 'Z' if self.next_run_at else None,
            'scheduled_task_name': self.scheduled_task_name,
            'created_at':      self.created_at.isoformat() + 'Z' if self.created_at else None,
        }


class BackupRun(db.Model):
    """Ejecución concreta de un job (o ad-hoc). Sirve también de historial."""
    __tablename__ = 'backup_runs'

    id          = db.Column(db.Integer, primary_key=True)
    job_id      = db.Column(db.Integer, db.ForeignKey('backup_jobs.id'), nullable=True, index=True)
    machine_id  = db.Column(db.Integer, db.ForeignKey('machines.id'), nullable=False, index=True)
    started_at  = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    status      = db.Column(db.String(20), nullable=False, default='running')  # running|completed|error|cancelled
    progress_pct        = db.Column(db.Float,   nullable=False, default=0.0)
    files_done          = db.Column(db.Integer, nullable=False, default=0)
    bytes_done          = db.Column(db.BigInteger, nullable=False, default=0)
    total_bytes_estimate= db.Column(db.BigInteger, nullable=False, default=0)
    duration_sec        = db.Column(db.Float, nullable=True)
    output      = db.Column(db.Text, nullable=True)
    error       = db.Column(db.Text, nullable=True)
    backup_full_name = db.Column(db.String(200), nullable=True)
    backup_path      = db.Column(db.String(500), nullable=True)
    # Snapshot del nombre/tipo del job en el momento de la ejecución.
    # Permite que la entrada del historial sobreviva si el job se elimina.
    job_name_snapshot   = db.Column(db.String(120), nullable=True)
    backup_type_snapshot= db.Column(db.String(20),  nullable=True)

    def to_dict(self):
        if self.job:
            job_name    = self.job.name
            backup_type = self.job.backup_type
        else:
            job_name    = self.job_name_snapshot or 'Trabajo eliminado'
            backup_type = self.backup_type_snapshot or 'full'
        return {
            'id':              self.id,
            'job_id':          self.job_id,
            'job_name':        job_name,
            'job_deleted':     self.job_id is None and self.job_name_snapshot is not None,
            'backup_type':     backup_type,
            'machine_id':      self.machine_id,
            'started_at':      self.started_at.isoformat() + 'Z' if self.started_at else None,
            'finished_at':     self.finished_at.isoformat() + 'Z' if self.finished_at else None,
            'status':          self.status,
            'progress_pct':    round(self.progress_pct or 0.0, 1),
            'files_done':      self.files_done,
            'bytes_done':      int(self.bytes_done or 0),
            'total_bytes_estimate': int(self.total_bytes_estimate or 0),
            'duration_sec':    self.duration_sec,
            'output':          self.output,
            'error':           self.error,
            'backup_full_name': self.backup_full_name,
            'backup_path':     self.backup_path,
        }


class MonitoredService(db.Model):
    """Servicio TCP/UDP monitorizado por ping a IP:puerto."""
    __tablename__ = 'monitored_services'

    id            = db.Column(db.Integer, primary_key=True)
    machine_id    = db.Column(db.Integer, db.ForeignKey('machines.id'), nullable=True, index=True)
    name          = db.Column(db.String(80),  nullable=False)
    icon_key      = db.Column(db.String(20),  nullable=True)   # winrm/iis/sql/rdp/dns/api/backup/...
    ip            = db.Column(db.String(45),  nullable=False)
    port          = db.Column(db.Integer,     nullable=False)
    protocol      = db.Column(db.String(8),   nullable=False, default='TCP')  # TCP|UDP|HTTPS
    enabled       = db.Column(db.Boolean,     nullable=False, default=True)
    last_status   = db.Column(db.String(16),  nullable=False, default='unknown')  # up|down|warning|unknown
    last_check    = db.Column(db.DateTime,    nullable=True)
    last_latency_ms = db.Column(db.Float,     nullable=True)
    last_message  = db.Column(db.Text,        nullable=True)
    created_at    = db.Column(db.DateTime,    default=datetime.utcnow)

    checks = db.relationship('ServiceCheck', backref='service', lazy='dynamic',
                             cascade='all, delete-orphan')

    def to_dict(self):
        m = db.session.get(Machine, self.machine_id) if self.machine_id else None
        return {
            'id':              self.id,
            'machine_id':      self.machine_id,
            'machine_name':    m.name if m else '—',
            'name':            self.name,
            'icon_key':        self.icon_key or '',
            'ip':              self.ip,
            'port':            self.port,
            'protocol':        self.protocol,
            'enabled':         self.enabled,
            'last_status':     self.last_status,
            'last_check':      self.last_check.isoformat() + 'Z' if self.last_check else None,
            'last_latency_ms': self.last_latency_ms,
            'last_message':    self.last_message,
        }


class ServiceCheck(db.Model):
    """Evento de cambio de estado o aviso de un servicio monitorizado."""
    __tablename__ = 'service_checks'

    id          = db.Column(db.Integer, primary_key=True)
    service_id  = db.Column(db.Integer, db.ForeignKey('monitored_services.id'), nullable=False, index=True)
    timestamp   = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    status      = db.Column(db.String(16), nullable=False)
    message     = db.Column(db.Text, nullable=True)
    latency_ms  = db.Column(db.Float, nullable=True)

    def to_dict(self):
        s = db.session.get(MonitoredService, self.service_id)
        m = db.session.get(Machine, s.machine_id) if (s and s.machine_id) else None
        return {
            'id':           self.id,
            'service_id':   self.service_id,
            'service_name': s.name if s else '—',
            'icon_key':     (s.icon_key or '') if s else '',
            'machine_name': m.name if m else (s.ip if s else '—'),
            'timestamp':    self.timestamp.isoformat() + 'Z' if self.timestamp else None,
            'status':       self.status,
            'message':      self.message or '',
            'latency_ms':   self.latency_ms,
        }


class EmailQueue(db.Model):
    """Cola persistente de correos pendientes de enviar.

    Permite reintentos tras reinicio y auditoría de envíos. El worker async
    (utils/mailer_worker.py) consume `status='queued'` con `scheduled_at<=now`
    y va marcando `sent` o `failed` con backoff exponencial.
    """
    __tablename__ = 'email_queue'

    id           = db.Column(db.Integer, primary_key=True)
    to_addr      = db.Column(EncryptedString(), nullable=False)   # PII — cifrado
    subject      = db.Column(db.String(200), nullable=False)
    body_html    = db.Column(EncryptedText(), nullable=False)     # contenido — cifrado
    body_text    = db.Column(EncryptedText(), nullable=True)      # contenido — cifrado
    # queued → sending → sent | failed
    status       = db.Column(db.String(16), nullable=False, default='queued', index=True)
    tries        = db.Column(db.Integer, nullable=False, default=0)
    last_error   = db.Column(db.Text, nullable=True)
    scheduled_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    sent_at      = db.Column(db.DateTime, nullable=True)
    created_at   = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    # Para anti-spam: agrupa envíos por (kind, related_id)
    related_kind = db.Column(db.String(40), nullable=True, index=True)
    related_id   = db.Column(db.Integer, nullable=True)

    def to_dict(self):
        return {
            'id':           self.id,
            'to':           self.to_addr,
            'subject':      self.subject,
            'status':       self.status,
            'tries':        self.tries,
            'last_error':   self.last_error,
            'scheduled_at': self.scheduled_at.isoformat() + 'Z' if self.scheduled_at else None,
            'sent_at':      self.sent_at.isoformat() + 'Z' if self.sent_at else None,
            'created_at':   self.created_at.isoformat() + 'Z' if self.created_at else None,
            'related_kind': self.related_kind,
            'related_id':   self.related_id,
        }


class NotificationPreference(db.Model):
    """Preferencias de notificación por email para un usuario concreto.

    Si no existe registro para un usuario, se aplican los defaults definidos
    en las columnas (todas las alertas críticas activadas).
    """
    __tablename__ = 'notification_preferences'

    id                = db.Column(db.Integer, primary_key=True)
    user_id           = db.Column(db.Integer, db.ForeignKey('users.id'),
                                  nullable=False, unique=True, index=True)
    machine_offline   = db.Column(db.Boolean, nullable=False, default=True)
    service_down      = db.Column(db.Boolean, nullable=False, default=True)
    backup_failed     = db.Column(db.Boolean, nullable=False, default=True)
    backup_completed  = db.Column(db.Boolean, nullable=False, default=True)
    daily_summary     = db.Column(db.Boolean, nullable=False, default=False)
    updated_at        = db.Column(db.DateTime, nullable=False,
                                  default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'user_id':          self.user_id,
            'machine_offline':  self.machine_offline,
            'service_down':     self.service_down,
            'backup_failed':    self.backup_failed,
            'backup_completed': self.backup_completed,
            'daily_summary':    self.daily_summary,
            'updated_at':       self.updated_at.isoformat() + 'Z' if self.updated_at else None,
        }
