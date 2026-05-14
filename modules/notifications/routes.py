"""Blueprint de notificaciones por email.

Endpoints (todos requieren autenticación; algunos sólo superadmin):
  POST /api/notifications/test           → envía email de prueba al usuario actual
  GET  /api/notifications/config         → muestra config SMTP (sin password)
"""
from datetime import datetime

from flask import Blueprint, jsonify, render_template
from flask_login import current_user

from config import Config
from modules.auth.decorators import require_role
from utils.mailer import send_email, is_valid_email
from utils.audit import log_action

notifications_bp = Blueprint('notifications', __name__)


@notifications_bp.route('/config', methods=['GET'])
@require_role('superadmin')
def get_config():
    """Estado actual de la config SMTP, sin exponer la contraseña."""
    return jsonify({
        'enabled':    Config.MAIL_ENABLED,
        'host':       Config.SMTP_HOST,
        'port':       Config.SMTP_PORT,
        'user':       Config.SMTP_USER,
        'has_password': bool(Config.SMTP_PASSWORD),
        'use_tls':    Config.SMTP_USE_TLS,
        'use_ssl':    Config.SMTP_USE_SSL,
        'timeout':    Config.SMTP_TIMEOUT,
        'from':       Config.MAIL_FROM,
        'from_name':  Config.MAIL_FROM_NAME,
    })


@notifications_bp.route('/test', methods=['POST'])
@require_role('superadmin')
def send_test_email():
    """Envía un email de prueba al email del usuario actual (superadmin)."""
    addr = (current_user.email or '').strip()
    if not addr:
        return jsonify({
            'ok': False,
            'error': "No tienes email configurado en tu perfil. Edita tu perfil y añade uno."
        }), 400
    if not is_valid_email(addr):
        return jsonify({
            'ok': False,
            'error': f"Dirección de email inválida: {addr}"
        }), 400

    if not Config.MAIL_ENABLED:
        return jsonify({
            'ok': False,
            'error': "MAIL_ENABLED=false en el servidor. Activa el envío en el .env."
        }), 400

    html = render_template(
        'emails/test.html',
        user=current_user,
        smtp_host=Config.SMTP_HOST,
        smtp_port=Config.SMTP_PORT,
        mail_from=Config.MAIL_FROM,
        sent_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    )
    ok = send_email(
        to=addr,
        subject='[Control Remoto] Email de prueba',
        html=html,
    )
    log_action(
        'email_test_sent' if ok else 'email_test_failed',
        f'user:{current_user.username}',
        f'to={addr} host={Config.SMTP_HOST}:{Config.SMTP_PORT}',
    )
    if ok:
        return jsonify({'ok': True, 'message': f'Email de prueba enviado a {addr}.'})
    return jsonify({
        'ok': False,
        'error': "El envío falló. Revisa el log de la app (utils/mailer.py) para el detalle del error SMTP."
    }), 500
