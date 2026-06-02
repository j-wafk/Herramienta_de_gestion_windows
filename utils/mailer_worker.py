# utils/mailer_worker.py
"""Worker en segundo plano que procesa la cola EmailQueue.

Cada 5 s lee filas con status='queued' y scheduled_at <= now, intenta enviarlas
con utils.mailer.send_email() y va marcando 'sent' o reprogramando con backoff
exponencial. Tras 5 intentos fallidos pasa a 'failed' y para.

Backoff: tries=1 → 30s, tries=2 → 2min, tries=3 → 10min, tries=4 → 1h.
"""
import logging
import threading
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 5
MAX_TRIES = 5
BATCH_SIZE = 20    # cuántos correos máx procesar por ciclo

# tries=0..4 → segundos hasta el siguiente intento
_BACKOFF_SEC = {1: 30, 2: 120, 3: 600, 4: 3600}


def _next_retry(tries: int) -> datetime:
    """Cuándo reintentar tras un fallo (segundo intento usa _BACKOFF_SEC[1])."""
    secs = _BACKOFF_SEC.get(tries, 3600)
    return datetime.utcnow() + timedelta(seconds=secs)


def run_one_cycle(app) -> int:
    """Procesa un lote de la cola. Devuelve cuántos correos se enviaron OK."""
    from database import db
    from database.models import EmailQueue
    from utils.mailer import send_email

    sent_ok = 0
    with app.app_context():
        now = datetime.utcnow()
        # Lock optimista: marcamos primero status='sending' uno a uno para evitar
        # que otro worker se lo lleve (si hubiera más de una instancia).
        pending = (EmailQueue.query
                   .filter(EmailQueue.status == 'queued')
                   .filter(EmailQueue.scheduled_at <= now)
                   .order_by(EmailQueue.scheduled_at.asc())
                   .limit(BATCH_SIZE)
                   .all())

        for q in pending:
            q.status = 'sending'
            db.session.commit()
            try:
                ok = send_email(
                    to=q.to_addr,
                    subject=q.subject,
                    html=q.body_html,
                    text=q.body_text,
                )
            except Exception as e:                  # noqa: BLE001 — robusto a lo que sea
                ok = False
                q.last_error = f'{type(e).__name__}: {e}'

            q.tries += 1
            if ok:
                q.status = 'sent'
                q.sent_at = datetime.utcnow()
                q.last_error = None
                sent_ok += 1
            else:
                if q.tries >= MAX_TRIES:
                    q.status = 'failed'
                    if not q.last_error:
                        q.last_error = 'fallos consecutivos al enviar SMTP'
                    logger.warning('[mailq] id=%d → failed tras %d intentos', q.id, q.tries)
                else:
                    q.status = 'queued'
                    q.scheduled_at = _next_retry(q.tries)
                    if not q.last_error:
                        q.last_error = 'fallo en send_email() — ver app.log'
                    logger.info('[mailq] id=%d retry %d en %s',
                                q.id, q.tries, q.scheduled_at.isoformat())
            db.session.commit()
    return sent_ok


def start_worker(app, interval=POLL_INTERVAL_SEC):
    """Arranca el thread daemon que procesa la cola."""
    def _loop():
        # Pequeño retraso para no chocar con migración/arranque
        time.sleep(3)
        while True:
            try:
                run_one_cycle(app)
            except Exception as e:                  # noqa: BLE001
                logger.error('[mailq] ciclo falló: %s', e)
            time.sleep(interval)

    t = threading.Thread(target=_loop, daemon=True, name='mailer-worker')
    t.start()
    logger.info('Worker de envío de emails iniciado (cada %ds, backoff hasta %d intentos)',
                interval, MAX_TRIES)
    return t
