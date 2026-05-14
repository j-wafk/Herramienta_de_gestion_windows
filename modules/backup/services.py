# modules/backup/services.py
"""
Servicios de orquestación de backups: ejecución asíncrona con progreso real
por polling y sincronización de tareas programadas con Task Scheduler.
"""
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta

from flask import current_app

from database import db
from database.models import BackupRun, BackupJob, BackupDestination, Machine
from utils.powershell_client import resolve_and_send
from .parsers import parse_backup_output, parse_size_output

logger = logging.getLogger(__name__)

# Tope máximo de entradas de historial por máquina.
HISTORY_MAX_PER_MACHINE = 100


def _parse_iso_dt(value):
    """Parsea una fecha ISO local del PS (sin tz). Devuelve None si falla."""
    if not value:
        return None
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(value, fmt)
        except (TypeError, ValueError):
            continue
    return None


def _create_run_from_entry(entry, job, machine_id, source_label):
    """Construye un BackupRun a partir de un dict y lo añade a la sesión."""
    started  = _parse_iso_dt(entry.get('started_at'))  or datetime.utcnow()
    finished = _parse_iso_dt(entry.get('finished_at')) or started
    bytes_done = int(entry.get('bytes') or 0)
    files_done = int(entry.get('files') or 0)
    status = entry.get('status') or 'completed'
    if status not in ('completed', 'error', 'cancelled'):
        status = 'completed'
    dest = entry.get('dest') or ''
    run = BackupRun(
        job_id=job.id,
        machine_id=machine_id,
        started_at=started,
        finished_at=finished,
        status=status,
        progress_pct=100.0 if status == 'completed' else 0.0,
        files_done=files_done,
        bytes_done=bytes_done,
        total_bytes_estimate=bytes_done,
        duration_sec=max(0.0, (finished - started).total_seconds()),
        output=f'Backup ejecutado por la tarea programada de Windows ({source_label})',
        error=entry.get('error'),
        backup_full_name=os.path.basename(dest) if dest else None,
        backup_path=dest or None,
        job_name_snapshot=job.name,
        backup_type_snapshot=job.backup_type,
    )
    db.session.add(run)
    return started


def _has_run_at(job_id, started, tolerance_sec=5):
    """¿Existe ya una BackupRun para este job alrededor de este started_at?"""
    delta = timedelta(seconds=tolerance_sec)
    return (BackupRun.query
            .filter(BackupRun.job_id == job_id,
                    BackupRun.started_at >= started - delta,
                    BackupRun.started_at <= started + delta)
            .first()) is not None


def import_scheduled_runs(machine_id: int) -> int:
    """Importa a `BackupRun` las ejecuciones realizadas por el Task Scheduler.

    Dos fuentes de datos:
    1. JSON marker files que el script genera (rápido, primario).
    2. Parseo de los log files de cada tarea (fallback robusto: Add-Content
       siempre escribe aunque haya problemas con permisos al crear JSON).

    Deduplicado por (job_id, started_at) con tolerancia de 5 s.
    """
    # Mapa task_name → BackupJob de esta máquina
    jobs = (BackupJob.query
            .filter_by(machine_id=machine_id)
            .filter(BackupJob.scheduled_task_name.isnot(None))
            .all())
    by_task = {j.scheduled_task_name: j for j in jobs}
    if not by_task:
        return 0

    imported = 0
    affected_jobs = set()

    def _process_jsonl(out, label):
        nonlocal imported
        if not (out and out.strip()):
            return
        for line in out.splitlines():
            line = line.strip()
            if not line.startswith('{'):
                continue
            try:
                entry = json.loads(line)
            except Exception as e:
                logger.warning(f"import_scheduled_runs[{label}]: línea no parseable: {line!r} ({e})")
                continue
            task = entry.get('task') or ''
            job = by_task.get(task)
            if not job:
                continue  # job ya borrado o no nuestro
            started_iso = entry.get('started_at')
            started = _parse_iso_dt(started_iso) or datetime.utcnow()
            if _has_run_at(job.id, started):
                continue  # ya importado por otra vía
            _create_run_from_entry(entry, job, machine_id, label)
            imported += 1
            affected_jobs.add(job.id)

    # 1) JSON marker files (consume y borra)
    try:
        out_json = resolve_and_send('pop_scheduled_runs', machine_id) or ''
        _process_jsonl(out_json, 'json')
    except Exception as e:
        logger.warning(f"import_scheduled_runs: pop_scheduled_runs falló: {e}")

    # 2) Log files (no consume, deduplica por started_at)
    try:
        out_log = resolve_and_send('scan_scheduled_runs', machine_id) or ''
        _process_jsonl(out_log, 'log')
    except Exception as e:
        logger.warning(f"import_scheduled_runs: scan_scheduled_runs falló: {e}")

    if imported:
        db.session.commit()
        for jid in affected_jobs:
            j = db.session.get(BackupJob, jid)
            if not j:
                continue
            last = (BackupRun.query.filter_by(job_id=j.id)
                    .order_by(BackupRun.started_at.desc()).first())
            if last:
                j.last_run_at = last.started_at
        db.session.commit()
        try:
            prune_history(machine_id)
        except Exception as e:
            logger.warning(f"prune_history tras import falló: {e}")
        logger.info(f"import_scheduled_runs: {imported} ejecuciones importadas (machine={machine_id})")

    return imported


def prune_history(machine_id: int, keep: int = HISTORY_MAX_PER_MACHINE) -> int:
    """Conserva sólo las `keep` últimas entradas de historial de la máquina.

    Devuelve el número de runs eliminadas. Nunca borra una run en estado
    'running' (podría romper un poller en curso).
    """
    total = BackupRun.query.filter_by(machine_id=machine_id).count()
    if total <= keep:
        return 0
    # Identificar los IDs a conservar (los más recientes).
    keep_ids = [r.id for r in (BackupRun.query
                .filter_by(machine_id=machine_id)
                .order_by(BackupRun.started_at.desc())
                .limit(keep)
                .all())]
    if not keep_ids:
        return 0
    deleted = (BackupRun.query
               .filter(BackupRun.machine_id == machine_id,
                       ~BackupRun.id.in_(keep_ids),
                       BackupRun.status != 'running')
               .delete(synchronize_session=False))
    db.session.commit()
    if deleted:
        logger.info(f"prune_history: {deleted} runs eliminadas de machine {machine_id}")
    return deleted


# ── Helpers de comandos PS ─────────────────────────────────────────────────────

def _quote(s):
    return '"' + str(s).replace('"', '') + '"'


def _ps_estimate(machine_id, path):
    out = resolve_and_send(f'estimate_size {_quote(path)}', machine_id)
    return parse_size_output(out)


def _ps_run_backup(machine_id, source, destination, full_name, btype, compress):
    cmd = f'backup {_quote(source)} {_quote(destination)} {full_name} {btype}'
    if compress:
        cmd += ' compress'
    return resolve_and_send(cmd, machine_id)


def _ps_verify(machine_id, backup_path):
    return resolve_and_send(f'verify_backup {_quote(backup_path)}', machine_id)


# ── Programación (Task Scheduler) ─────────────────────────────────────────────

class ScheduleError(RuntimeError):
    """Error al registrar la tarea en Task Scheduler. El mensaje incluye el output del PS."""


def schedule_job_in_ps(job: BackupJob) -> str:
    """Registra/actualiza la tarea en el Task Scheduler de la máquina del job.

    Devuelve el nombre real de la tarea (con prefijo GestionBackup_).
    Lanza ScheduleError con el output del PS si Windows rechaza el registro.
    Devuelve '' si el job es manual/deshabilitado y no procede programar.
    """
    if job.schedule == 'manual' or not job.enabled:
        return ''
    dest = BackupDestination.query.get(job.destination_id)
    if not dest:
        return ''
    compress_arg = 'true' if job.compress else 'false'
    cmd = (
        f'schedule_backup "{job.name}" {_quote(job.source_path)} '
        f'{_quote(dest.path)} {job.schedule} {job.schedule_time} {job.backup_type} '
        f'{compress_arg}'
    )
    out = resolve_and_send(cmd, job.machine_id) or ''
    low = out.lower()
    if low.startswith('error') or 'error al registrar' in low or 'no aparece' in low:
        logger.warning(f"schedule_backup falló: {out!r}")
        raise ScheduleError(out.strip())
    if 'programado exitosamente' in low or 'scheduled' in low:
        return f'GestionBackup_{job.name}'
    logger.warning(f"schedule_backup respondió inesperado: {out!r}")
    raise ScheduleError(out.strip() or 'Respuesta inesperada del servidor PowerShell')


def unschedule_job_in_ps(job: BackupJob):
    """Elimina la tarea del Task Scheduler. Silencioso si no existía."""
    name = job.scheduled_task_name or f'GestionBackup_{job.name}'
    short = name.replace('GestionBackup_', '')
    if not short:
        return
    resolve_and_send(f'delete_scheduled_backup "{short}"', job.machine_id)


def compute_next_run(schedule: str, hhmm: str, now=None) -> datetime:
    """Calcula la próxima ejecución a partir de schedule y hora HH:MM."""
    now = now or datetime.now()
    try:
        h, m = map(int, hhmm.split(':'))
    except Exception:
        h, m = 2, 0
    nxt = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if schedule == 'daily':
        if nxt <= now:
            nxt += timedelta(days=1)
    elif schedule == 'weekly':
        # Mismo comportamiento que el script PS: dispara los lunes
        days_ahead = (0 - nxt.weekday()) % 7  # 0 = Monday
        if days_ahead == 0 and nxt <= now:
            days_ahead = 7
        nxt += timedelta(days=days_ahead)
    elif schedule == 'monthly':
        # Día 1 del mes siguiente (mismo comportamiento que PS)
        if nxt.month == 12:
            nxt = nxt.replace(year=nxt.year + 1, month=1, day=1)
        else:
            nxt = nxt.replace(month=nxt.month + 1, day=1)
    else:
        return None
    return nxt


# ── Ejecución asíncrona ────────────────────────────────────────────────────────

def start_backup_run(job: BackupJob, ad_hoc: bool = False) -> BackupRun:
    """Crea un BackupRun en estado 'running' y lanza un hilo que lo ejecuta."""
    if not ad_hoc and not job.enabled:
        raise ValueError("El trabajo está desactivado. Actívalo antes de ejecutarlo.")

    run = BackupRun(
        job_id=job.id,
        machine_id=job.machine_id,
        started_at=datetime.utcnow(),
        status='running',
        progress_pct=0.0,
        job_name_snapshot=job.name,
        backup_type_snapshot=job.backup_type,
    )
    db.session.add(run)
    db.session.commit()

    app = current_app._get_current_object()
    t = threading.Thread(
        target=_execute_run,
        args=(run.id, app),
        daemon=True,
        name=f'backup-run-{run.id}',
    )
    t.start()
    return run


def _execute_run(run_id: int, app):
    """Hilo de ejecución del backup. Actualiza el BackupRun y, al final, el job."""
    with app.app_context():
        run = db.session.get(BackupRun, run_id)
        if not run:
            return
        job = db.session.get(BackupJob, run.job_id) if run.job_id else None
        if not job:
            run.status = 'error'
            run.error = 'Trabajo no encontrado'
            run.finished_at = datetime.utcnow()
            db.session.commit()
            return
        dest = db.session.get(BackupDestination, job.destination_id)
        if not dest:
            run.status = 'error'
            run.error = 'Destino no encontrado'
            run.finished_at = datetime.utcnow()
            db.session.commit()
            return
        if dest.type != 'local':
            run.status = 'error'
            run.error = f'Destinos de tipo {dest.type} no están soportados todavía.'
            run.finished_at = datetime.utcnow()
            db.session.commit()
            return

        machine_id = job.machine_id
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_full_name = f"{job.name}_{timestamp}"
        backup_path = dest.path.rstrip('\\') + '\\' + backup_full_name + (
            '.zip' if job.compress else ''
        )
        run.backup_full_name = backup_full_name
        run.backup_path = backup_path

        try:
            estimate = _ps_estimate(machine_id, job.source_path)
            run.total_bytes_estimate = estimate.get('bytes') or 0
            db.session.commit()
        except Exception as e:
            logger.warning(f"No se pudo estimar tamaño: {e}")

        # Poller de progreso: mira el tamaño del destino mientras corre
        stop_flag = {'stop': False}

        def _poll():
            while not stop_flag['stop']:
                try:
                    with app.app_context():
                        r = db.session.get(BackupRun, run_id)
                        if not r or r.status != 'running':
                            return
                        size = _ps_estimate(machine_id, backup_path)
                        bytes_done = size.get('bytes') or 0
                        files_done = size.get('files') or 0
                        total = r.total_bytes_estimate or 0
                        pct = (bytes_done / total * 100.0) if total > 0 else 0.0
                        # Limita a 95 % hasta que el comando termine
                        if pct > 95.0:
                            pct = 95.0
                        r.bytes_done = bytes_done
                        r.files_done = files_done
                        r.progress_pct = pct
                        db.session.commit()
                except Exception as e:
                    logger.debug(f"poller backup {run_id}: {e}")
                time.sleep(2.0)

        poller = threading.Thread(target=_poll, daemon=True, name=f'backup-poll-{run_id}')
        poller.start()

        try:
            output = _ps_run_backup(
                machine_id=machine_id,
                source=job.source_path,
                destination=dest.path,
                full_name=backup_full_name,
                btype=job.backup_type,
                compress=job.compress,
            )
        except Exception as e:
            output = f"Error inesperado: {e}"
        finally:
            stop_flag['stop'] = True

        result = parse_backup_output(output)
        success = bool(result.get('success'))
        run.output = output
        run.error = result.get('error')
        run.files_done = result.get('files_processed') or run.files_done

        # Verificación opcional
        if success and job.verify_after:
            try:
                verify_out = _ps_verify(machine_id, backup_path)
                run.output = (run.output or '') + "\n\n--- Verificación ---\n" + (verify_out or '')
                if 'verificado' not in (verify_out or '').lower():
                    success = False
                    run.error = (run.error or '') + ' | Verificación falló'
            except Exception as e:
                logger.warning(f"verify_backup error: {e}")

        run.finished_at = datetime.utcnow()
        run.duration_sec = (run.finished_at - run.started_at).total_seconds()
        run.progress_pct = 100.0 if success else run.progress_pct
        run.status = 'completed' if success else 'error'

        # Actualizar job
        job.last_run_at = run.finished_at
        if job.schedule != 'manual':
            job.next_run_at = compute_next_run(job.schedule, job.schedule_time)

        db.session.commit()

        # Notificaciones por email (encolan en EmailQueue; el worker las envía)
        try:
            from modules.notifications.dispatch import (
                notify_backup_completed, notify_backup_failed,
            )
            from database.models import Machine
            mach = db.session.get(Machine, machine_id)
            mname = mach.name if mach else None
            if success:
                dur = run.duration_sec or 0
                dur_str = f"{int(dur)} s" if dur < 90 else f"{dur/60:.1f} min"
                files = int(run.files_done or 0)
                bytes_done = int(run.bytes_done or 0)
                size_str = (
                    f"{bytes_done/1024/1024/1024:.2f} GB" if bytes_done >= (1<<30) else
                    f"{bytes_done/1024/1024:.1f} MB"     if bytes_done >= (1<<20) else
                    f"{bytes_done/1024:.1f} KB"          if bytes_done >= 1024    else
                    f"{bytes_done} B"
                )
                notify_backup_completed(run, job.name, machine_name=mname,
                                        size_str=size_str, files=files,
                                        duration_str=dur_str)
            else:
                notify_backup_failed(run, job.name, machine_name=mname)
        except Exception as e:                          # noqa: BLE001
            logger.warning(f"notify backup falló: {e}")

        # Poda del historial al máximo permitido por máquina
        try:
            prune_history(machine_id)
        except Exception as e:
            logger.warning(f"prune_history falló: {e}")
