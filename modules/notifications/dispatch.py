"""Helpers para disparar notificaciones por email desde eventos del sistema.

Cada función:
  1. Resuelve los destinatarios consultando NotificationPreference + User.email
  2. Renderiza la plantilla Jinja correspondiente
  3. Encola un EmailQueue por destinatario via send_email_async()

Diseñado para llamarse desde el poller, módulos de backup, auth, etc.
"""
import logging
from datetime import datetime

from flask import render_template

from database.models import User, NotificationPreference
from utils.mailer import send_email_async

logger = logging.getLogger(__name__)


def _recipients_for(pref_attr: str):
    """Devuelve la lista de emails (str) de usuarios que tienen activado
    `pref_attr` en sus preferencias.

    Si un usuario no tiene fila en NotificationPreference se toma el DEFAULT
    de la columna (todas las alertas críticas True salvo backup_completed).
    """
    # Mapa de defaults por atributo (debe coincidir con el modelo)
    defaults = {
        'machine_offline':  True,
        'service_down':     True,
        'backup_failed':    True,
        'backup_completed': True,    # también el OK por defecto (cambiable por usuario)
        'daily_summary':    False,
    }
    default_value = defaults.get(pref_attr, False)

    users = User.query.filter(User.is_active.is_(True),
                              User.email.isnot(None)).all()
    if not users:
        return []

    # Preferencias por user_id
    prefs = {p.user_id: p for p in NotificationPreference.query.all()}

    out = []
    for u in users:
        p = prefs.get(u.id)
        if p is None:
            enabled = default_value
        else:
            enabled = bool(getattr(p, pref_attr, default_value))
        if enabled and u.email:
            out.append(u.email)
    return out


def _ts_now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


_BACKUP_TYPE_LABELS = {
    'full':         'Completa',
    'complete':     'Completa',
    'incremental':  'Incremental',
    'differential': 'Diferencial',
}


def _backup_type_label(raw):
    """Traduce el valor interno del tipo de backup a una etiqueta en español."""
    return _BACKUP_TYPE_LABELS.get((raw or '').lower(), 'Completa')


# â”€â”€â”€ Eventos concretos â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def notify_machine_offline(machine):
    """Encola un email a cada usuario suscrito cuando una máquina pasa a offline."""
    recipients = _recipients_for('machine_offline')
    if not recipients:
        return 0
    try:
        html = render_template(
            'emails/machine_offline.html',
            machine=machine,
            last_seen=machine.last_seen.strftime('%Y-%m-%d %H:%M:%S') if machine.last_seen else None,
            detected_at=_ts_now(),
        )
    except Exception as e:                              # noqa: BLE001
        logger.error('[notify] render machine_offline falló: %s', e)
        return 0
    subject = f'[Control Remoto] Máquina sin conexión: {machine.name}'
    sent = 0
    for addr in recipients:
        if send_email_async(addr, subject, html,
                            related_kind='machine_offline',
                            related_id=machine.id):
            sent += 1
    logger.info('[notify] machine_offline %s â†’ %d encolados', machine.name, sent)
    return sent


def notify_service_down(service, prev_status, machine_name=None):
    """Encola un email cuando un MonitoredService pasa de up/warning â†’ down."""
    recipients = _recipients_for('service_down')
    if not recipients:
        return 0
    try:
        html = render_template(
            'emails/service_down.html',
            service=service,
            machine_name=machine_name,
            prev_status=prev_status,
            message=service.last_message,
            detected_at=_ts_now(),
        )
    except Exception as e:                              # noqa: BLE001
        logger.error('[notify] render service_down falló: %s', e)
        return 0
    subject = f'[Control Remoto] Servicio caído: {service.name}'
    sent = 0
    for addr in recipients:
        if send_email_async(addr, subject, html,
                            related_kind='service_down',
                            related_id=service.id):
            sent += 1
    logger.info('[notify] service_down %s â†’ %d encolados', service.name, sent)
    return sent


def notify_backup_failed(run, job_name, machine_name=None):
    """Cuando un BackupRun pasa a status='error'."""
    recipients = _recipients_for('backup_failed')
    if not recipients:
        return 0
    try:
        html = render_template(
            'emails/backup_failed.html',
            job_name=job_name,
            machine_name=machine_name,
            started_at=run.started_at.strftime('%Y-%m-%d %H:%M:%S') if run.started_at else 'â€”',
            finished_at=run.finished_at.strftime('%Y-%m-%d %H:%M:%S') if run.finished_at else None,
            backup_type=_backup_type_label(getattr(run, 'backup_type_snapshot', None)),
            error=run.error,
        )
    except Exception as e:                              # noqa: BLE001
        logger.error('[notify] render backup_failed falló: %s', e)
        return 0
    subject = f'[Control Remoto] Backup fallido: {job_name}'
    sent = 0
    for addr in recipients:
        if send_email_async(addr, subject, html,
                            related_kind='backup_failed',
                            related_id=run.id):
            sent += 1
    logger.info('[notify] backup_failed run=%d â†’ %d encolados', run.id, sent)
    return sent


def notify_backup_completed(run, job_name, machine_name=None,
                            size_str='â€”', files=0, duration_str='â€”'):
    """Cuando un BackupRun pasa a status='completed'."""
    recipients = _recipients_for('backup_completed')
    if not recipients:
        return 0
    try:
        html = render_template(
            'emails/backup_completed.html',
            job_name=job_name,
            machine_name=machine_name,
            started_at=run.started_at.strftime('%Y-%m-%d %H:%M:%S') if run.started_at else 'â€”',
            finished_at=run.finished_at.strftime('%Y-%m-%d %H:%M:%S') if run.finished_at else 'â€”',
            duration=duration_str,
            size=size_str,
            files=files,
            backup_type=_backup_type_label(getattr(run, 'backup_type_snapshot', None)),
        )
    except Exception as e:                              # noqa: BLE001
        logger.error('[notify] render backup_completed falló: %s', e)
        return 0
    subject = f'[Control Remoto] Backup completado: {job_name}'
    sent = 0
    for addr in recipients:
        if send_email_async(addr, subject, html,
                            related_kind='backup_completed',
                            related_id=run.id):
            sent += 1
    return sent


def notify_welcome(user):
    """Email al usuario recién creado. Siempre se envía (no respeta preferencias)."""
    if not user.email:
        return 0
    try:
        html = render_template(
            'emails/welcome.html',
            user=user,
            created_at=_ts_now(),
        )
    except Exception as e:                              # noqa: BLE001
        logger.error('[notify] render welcome falló: %s', e)
        return 0
    return send_email_async(
        user.email,
        f'[Control Remoto] Bienvenido, {user.username}',
        html,
        related_kind='welcome',
        related_id=user.id,
        cooldown_minutes=0,                  # nunca aplicar cooldown a bienvenida
    )


def notify_password_changed(user, ip=None):
    """Confirma al usuario que su contraseña cambió. No respeta preferencias (seguridad)."""
    if not user.email:
        return 0
    try:
        html = render_template(
            'emails/password_changed.html',
            user=user,
            ip=ip,
            changed_at=_ts_now(),
        )
    except Exception as e:                              # noqa: BLE001
        logger.error('[notify] render password_changed falló: %s', e)
        return 0
    return send_email_async(
        user.email,
        '[Control Remoto] Tu contraseña ha cambiado',
        html,
        related_kind='password_changed',
        related_id=user.id,
        cooldown_minutes=0,                  # cada cambio se notifica
    )
