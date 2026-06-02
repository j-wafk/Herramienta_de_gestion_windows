"""
Envía un correo de prueba de CADA tipo a MailHog para poder revisarlos.

Uso (dentro del contenedor Flask):
    docker compose exec flask python scripts/send_test_emails.py

O desde el host (si Flask corre en local):
    python scripts/send_test_emails.py
"""
import sys
import os
from datetime import datetime
from types import SimpleNamespace

# Asegura que la raíz del proyecto esté en el path
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, _ROOT)

# Carga el .env antes de importar config (para ejecución local sin Docker)
from dotenv import load_dotenv
load_dotenv(os.path.join(_ROOT, '.env'))

from main import create_app
from utils.mailer import send_email

_smtp_user = os.getenv('SMTP_USER', '').strip()
DEST = os.getenv('TEST_MAIL_TO') or (_smtp_user if _smtp_user else 'test@mailhog.local')

app = create_app()


def _send(subject, template, **ctx):
    with app.app_context():
        from flask import render_template
        html = render_template(template, **ctx)
    ok = send_email(DEST, subject, html)
    estado = 'OK' if ok else 'FALLO'
    print(f"  [{estado}] {subject}")
    return ok


def main():
    now = datetime.now()
    fmt = now.strftime('%Y-%m-%d %H:%M:%S')

    print(f"\nEnviando emails de prueba a → {DEST}")
    print("=" * 55)

    # 1. Bienvenida
    _send(
        '[Control Remoto] Bienvenido, admin',
        'emails/welcome.html',
        user=SimpleNamespace(username='admin', role='superadmin'),
        created_at=fmt,
    )

    # 2. Contraseña cambiada
    _send(
        '[Control Remoto] Tu contraseña ha cambiado',
        'emails/password_changed.html',
        user=SimpleNamespace(username='admin'),
        ip='192.168.1.10',
        changed_at=fmt,
    )

    # 3. Máquina sin conexión
    _send(
        '[Control Remoto] Máquina sin conexión: Servidor-Produccion',
        'emails/machine_offline.html',
        machine=SimpleNamespace(name='Servidor-Produccion', ip='192.168.1.50'),
        last_seen=fmt,
        detected_at=fmt,
    )

    # 4. Servicio caído
    _send(
        '[Control Remoto] Servicio caído: nginx',
        'emails/service_down.html',
        service=SimpleNamespace(name='nginx', port=80, protocol='TCP',
                                last_message='Connection refused'),
        machine_name='Servidor-Produccion',
        prev_status='up',
        message='Connection refused',
        detected_at=fmt,
    )

    # 5. Backup fallido
    run_fail = SimpleNamespace(
        started_at=now,
        finished_at=now,
        error='No space left on device',
        backup_type_snapshot='full',
    )
    _send(
        '[Control Remoto] Backup fallido: backup-diario',
        'emails/backup_failed.html',
        job_name='backup-diario',
        machine_name='Servidor-Produccion',
        started_at=fmt,
        finished_at=fmt,
        backup_type='full',
        error='No space left on device',
    )

    # 6. Backup completado
    run_ok = SimpleNamespace(
        started_at=now,
        finished_at=now,
        backup_type_snapshot='full',
    )
    _send(
        '[Control Remoto] Backup completado: backup-diario',
        'emails/backup_completed.html',
        job_name='backup-diario',
        machine_name='Servidor-Produccion',
        started_at=fmt,
        finished_at=fmt,
        duration='1m 23s',
        size='2.4 GB',
        files=1840,
        backup_type='full',
    )

    print("=" * 55)
    print(f"Abre MailHog en http://localhost:18025 para verlos.\n")


if __name__ == '__main__':
    main()
