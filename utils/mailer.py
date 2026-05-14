# utils/mailer.py
"""Envío síncrono de correos vía SMTP.

Uso típico:
    from utils.mailer import send_email
    send_email(
        to='admin@empresa.com',
        subject='Alerta',
        html='<p>contenido</p>',
        text='contenido en plano (opcional)'
    )

Si MAIL_ENABLED=False, send_email() es no-op y devuelve True (útil en dev).
"""
import re
import smtplib
import socket
import ssl
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid

from config import Config

logger = logging.getLogger(__name__)

# RFC-5322 simplificado: suficiente para filtrar errores obvios.
_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')


class MailerError(Exception):
    """Fallo al enviar email (timeout, auth, conexión, etc.)."""


def is_valid_email(addr: str) -> bool:
    """Validación rápida de dirección de correo."""
    return bool(addr) and bool(_EMAIL_RE.match(addr.strip()))


def _html_to_text(html: str) -> str:
    """Fallback muy básico: quita etiquetas para el cuerpo text/plain."""
    if not html:
        return ''
    return re.sub(r'<[^>]+>', '', html).strip()


def send_email(to, subject: str, html: str, text: str = None) -> bool:
    """Envía un correo via SMTP. Devuelve True en éxito, False en fallo.

    `to`: str o lista de str.
    `subject`: línea de asunto.
    `html`: cuerpo HTML. Si `text` no se da, se genera quitando tags.

    Lanza MailerError sólo si hay un fallo de programación grave (ej. dirección
    inválida). Fallos de SMTP se devuelven como False con log.
    """
    if not Config.MAIL_ENABLED:
        logger.info("[mailer] MAIL_ENABLED=false → no se envía (asunto: %r)", subject)
        return True

    # Normalizar destinatarios
    if isinstance(to, str):
        recipients = [to.strip()]
    elif isinstance(to, (list, tuple, set)):
        recipients = [str(x).strip() for x in to if x]
    else:
        raise MailerError(f"to debe ser str o lista, recibido: {type(to)}")
    recipients = [r for r in recipients if r]

    if not recipients:
        logger.warning("[mailer] sin destinatarios — no se envía")
        return False

    invalid = [r for r in recipients if not is_valid_email(r)]
    if invalid:
        logger.warning("[mailer] direcciones inválidas, se omiten: %s", invalid)
        recipients = [r for r in recipients if r not in invalid]
        if not recipients:
            return False

    if not subject:
        subject = '(sin asunto)'
    if not html:
        html = '<p>(mensaje vacío)</p>'
    if not text:
        text = _html_to_text(html)

    # Construir mensaje MIME multipart/alternative
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = formataddr((Config.MAIL_FROM_NAME, Config.MAIL_FROM))
    msg['To'] = ', '.join(recipients)
    msg['Message-ID'] = make_msgid(domain=(Config.MAIL_FROM.split('@', 1)[-1] or 'localhost'))
    msg.attach(MIMEText(text, 'plain', _charset='utf-8'))
    msg.attach(MIMEText(html, 'html', _charset='utf-8'))

    try:
        if Config.SMTP_USE_SSL:
            ctx = ssl.create_default_context()
            smtp = smtplib.SMTP_SSL(
                Config.SMTP_HOST,
                Config.SMTP_PORT,
                timeout=Config.SMTP_TIMEOUT,
                context=ctx,
            )
        else:
            smtp = smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT,
                                timeout=Config.SMTP_TIMEOUT)

        with smtp:
            smtp.ehlo()
            if Config.SMTP_USE_TLS and not Config.SMTP_USE_SSL:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if Config.SMTP_USER and Config.SMTP_PASSWORD:
                smtp.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
            refused = smtp.sendmail(Config.MAIL_FROM, recipients, msg.as_string())
            if refused:
                logger.warning("[mailer] destinatarios rechazados: %s", refused)

        logger.info("[mailer] enviado: subject=%r to=%s", subject, recipients)
        return True

    except (smtplib.SMTPException, socket.timeout, socket.gaierror, OSError, ssl.SSLError) as e:
        logger.error("[mailer] FALLO envío (%s): %s | host=%s:%s",
                     type(e).__name__, e, Config.SMTP_HOST, Config.SMTP_PORT)
        return False


# ─── Envío asíncrono (encola en EmailQueue) ────────────────────────────────
# Cooldown por defecto entre dos envíos del mismo (kind, related_id):
# evita inundar con la misma alerta cuando un servicio flapping va y viene.
DEFAULT_COOLDOWN_MINUTES = 15


def send_email_async(
    to,
    subject: str,
    html: str,
    text: str = None,
    related_kind: str = None,
    related_id: int = None,
    cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES,
) -> int:
    """Encola un email para que el worker lo envíe en background.

    Devuelve el id de la fila en EmailQueue (>0) si se encoló, o 0 si se descartó
    (cooldown, destino inválido, MAIL_ENABLED=false, etc.).

    `related_kind` + `related_id` permiten anti-spam: si en los últimos
    `cooldown_minutes` ya hay un correo encolado/enviado con el mismo par,
    no se vuelve a encolar.

    Esta función NO bloquea: solo escribe en la BD. El envío real lo hace el
    worker (utils/mailer_worker.py).
    """
    if not Config.MAIL_ENABLED:
        logger.debug("[mailer] async no-op: MAIL_ENABLED=false")
        return 0

    addr = (to or '').strip() if isinstance(to, str) else ''
    if isinstance(to, (list, tuple, set)):
        # encolar un email por destinatario para que el cooldown trabaje por persona
        rid = 0
        for r in to:
            rid = send_email_async(r, subject, html, text,
                                   related_kind, related_id, cooldown_minutes) or rid
        return rid
    if not is_valid_email(addr):
        logger.warning("[mailer] async: destinatario inválido %r", to)
        return 0

    # Importación tardía para evitar ciclos al cargar el módulo
    from datetime import datetime, timedelta
    from database import db
    from database.models import EmailQueue

    # Anti-spam por (kind, related_id, recipient)
    if related_kind and related_id is not None and cooldown_minutes > 0:
        cutoff = datetime.utcnow() - timedelta(minutes=cooldown_minutes)
        recent = (EmailQueue.query
                  .filter(EmailQueue.related_kind == related_kind)
                  .filter(EmailQueue.related_id == related_id)
                  .filter(EmailQueue.to_addr == addr)
                  .filter(EmailQueue.created_at >= cutoff)
                  .filter(EmailQueue.status.in_(('queued', 'sending', 'sent')))
                  .first())
        if recent:
            logger.info("[mailer] async cooldown: %s/%s/%s ya encolado en últimos %dmin (id=%d)",
                        related_kind, related_id, addr, cooldown_minutes, recent.id)
            return 0

    if not subject:
        subject = '(sin asunto)'
    if not html:
        html = '<p>(mensaje vacío)</p>'
    if not text:
        text = _html_to_text(html)

    row = EmailQueue(
        to_addr=addr,
        subject=subject[:200],
        body_html=html,
        body_text=text,
        status='queued',
        tries=0,
        related_kind=related_kind,
        related_id=related_id,
    )
    try:
        db.session.add(row)
        db.session.commit()
        logger.info("[mailer] async encolado id=%d → %s (%r)", row.id, addr, subject)
        return row.id
    except Exception as e:                          # noqa: BLE001
        db.session.rollback()
        logger.error("[mailer] async error al encolar: %s", e)
        return 0
