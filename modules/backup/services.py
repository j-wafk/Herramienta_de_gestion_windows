# modules/backup/services.py
"""
Servicios de orquestaciÃ³n de backups: ejecuciÃ³n asÃ­ncrona con progreso real
por polling y sincronizaciÃ³n de tareas programadas con Task Scheduler.
"""
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta

from flask import current_app

from database import db
from database.models import BackupRun, BackupJob, BackupDestination
from utils.powershell_client import resolve_and_send
from .parsers import parse_backup_output, parse_size_output

logger = logging.getLogger(__name__)

# Tope mÃ¡ximo de entradas de historial por mÃ¡quina.
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
    """Construye un BackupRun a partir de un dict y lo aÃ±ade a la sesiÃ³n."""
    started = _parse_iso_dt(entry.get('started_at')) or datetime.utcnow()
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
    """Â¿Existe ya una BackupRun para este job alrededor de este started_at?"""
    delta = timedelta(seconds=tolerance_sec)
    return (BackupRun.query
            .filter(BackupRun.job_id == job_id,
                    BackupRun.started_at >= started - delta,
                    BackupRun.started_at <= started + delta)
            .first()) is not None


def import_scheduled_runs(machine_id: int) -> int:
    """Importa a `BackupRun` las ejecuciones realizadas por el Task Scheduler.

    Dos fuentes de datos:
    1. JSON marker files que el script genera (rÃ¡pido, primario).
    2. Parseo de los log files de cada tarea (fallback robusto: Add-Content
       siempre escribe aunque haya problemas con permisos al crear JSON).

    Deduplicado por (job_id, started_at) con tolerancia de 5 s.
    """
    # Mapa task_name â†’ BackupJob de esta mÃ¡quina
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
                logger.warning(f"import_scheduled_runs[{label}]: lÃ­nea no parseable: {line!r} ({e})")
                continue
            task = entry.get('task') or ''
            job = by_task.get(task)
            if not job:
                continue  # job ya borrado o no nuestro
            started_iso = entry.get('started_at')
            started = _parse_iso_dt(started_iso) or datetime.utcnow()
            if _has_run_at(job.id, started):
                continue  # ya importado por otra vÃ­a
            _create_run_from_entry(entry, job, machine_id, label)
            imported += 1
            affected_jobs.add(job.id)

    # 1) JSON marker files (consume y borra)
    try:
        out_json = resolve_and_send('pop_scheduled_runs', machine_id) or ''
        _process_jsonl(out_json, 'json')
    except Exception as e:
        logger.warning(f"import_scheduled_runs: pop_scheduled_runs fallÃ³: {e}")

    # 2) Log files (no consume, deduplica por started_at)
    try:
        out_log = resolve_and_send('scan_scheduled_runs', machine_id) or ''
        _process_jsonl(out_log, 'log')
    except Exception as e:
        logger.warning(f"import_scheduled_runs: scan_scheduled_runs fallÃ³: {e}")

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
            logger.warning(f"prune_history tras import fallÃ³: {e}")
        logger.info(f"import_scheduled_runs: {imported} ejecuciones importadas (machine={machine_id})")

    return imported


def prune_history(machine_id: int, keep: int = HISTORY_MAX_PER_MACHINE) -> int:
    """Conserva sÃ³lo las `keep` Ãºltimas entradas de historial de la mÃ¡quina.

    Devuelve el nÃºmero de runs eliminadas. Nunca borra una run en estado
    'running' (podrÃ­a romper un poller en curso).
    """
    total = BackupRun.query.filter_by(machine_id=machine_id).count()
    if total <= keep:
        return 0
    # Identificar los IDs a conservar (los mÃ¡s recientes).
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


# â”€â”€ Helpers de comandos PS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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


# â”€â”€ ProgramaciÃ³n (Task Scheduler) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class ScheduleError(RuntimeError):
    """Error al registrar la tarea en Task Scheduler. El mensaje incluye el output del PS."""


def schedule_job_in_ps(job: BackupJob) -> str:
    """Registra/actualiza la tarea en el Task Scheduler de la mÃ¡quina del job.

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
        logger.warning(f"schedule_backup fallÃ³: {out!r}")
        raise ScheduleError(out.strip())
    if 'programado exitosamente' in low or 'scheduled' in low:
        return f'GestionBackup_{job.name}'
    logger.warning(f"schedule_backup respondiÃ³ inesperado: {out!r}")
    raise ScheduleError(out.strip() or 'Respuesta inesperada del servidor PowerShell')


def unschedule_job_in_ps(job: BackupJob):
    """Elimina la tarea del Task Scheduler. Silencioso si no existÃ­a."""
    name = job.scheduled_task_name or f'GestionBackup_{job.name}'
    short = name.replace('GestionBackup_', '')
    if not short:
        return
    resolve_and_send(f'delete_scheduled_backup "{short}"', job.machine_id)


def compute_next_run(schedule: str, hhmm: str, now=None) -> datetime:
    """Calcula la prÃ³xima ejecuciÃ³n a partir de schedule y hora HH:MM."""
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
        # DÃ­a 1 del mes siguiente (mismo comportamiento que PS)
        if nxt.month == 12:
            nxt = nxt.replace(year=nxt.year + 1, month=1, day=1)
        else:
            nxt = nxt.replace(month=nxt.month + 1, day=1)
    else:
        return None
    return nxt


# â”€â”€ EjecuciÃ³n asÃ­ncrona â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def start_backup_run(job: BackupJob, ad_hoc: bool = False) -> BackupRun:
    """Crea un BackupRun en estado 'running' y lanza un hilo que lo ejecuta."""
    if not ad_hoc and not job.enabled:
        raise ValueError("El trabajo estÃ¡ desactivado. ActÃ­valo antes de ejecutarlo.")

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
    """Hilo de ejecuciÃ³n del backup. Actualiza el BackupRun y, al final, el job."""
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
            run.error = f'Destinos de tipo {dest.type} no estÃ¡n soportados todavÃ­a.'
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
            logger.warning(f"No se pudo estimar tamaÃ±o: {e}")

        # Poller de progreso: mira el tamaÃ±o del destino mientras corre
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
        run.bytes_done = result.get('bytes_processed') or run.bytes_done

        # Medir tamaÃ±o real del destino tras la copia (mÃ¡s fiable que el parser)
        if success:
            try:
                final_size = _ps_estimate(machine_id, backup_path)
                if final_size.get('bytes'):
                    run.bytes_done = final_size['bytes']
                    run.files_done = final_size.get('files') or run.files_done
            except Exception as e:
                logger.debug(f"No se pudo medir destino final: {e}")

        # VerificaciÃ³n opcional
        if success and job.verify_after:
            try:
                verify_out = _ps_verify(machine_id, backup_path)
                run.output = (run.output or '') + "\n\n--- VerificaciÃ³n ---\n" + (verify_out or '')
                if 'verificado' not in (verify_out or '').lower():
                    success = False
                    run.error = (run.error or '') + ' | VerificaciÃ³n fallÃ³'
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

        # Notificaciones por email: solo si el job tiene notify=True
        if job.notify:
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
                        f"{bytes_done/1024/1024/1024:.2f} GB" if bytes_done >= (1 << 30) else
                        f"{bytes_done/1024/1024:.1f} MB" if bytes_done >= (1 << 20) else
                        f"{bytes_done/1024:.1f} KB" if bytes_done >= 1024 else
                        f"{bytes_done} B"
                    )
                    notify_backup_completed(run, job.name, machine_name=mname,
                                            size_str=size_str, files=files,
                                            duration_str=dur_str)
                else:
                    notify_backup_failed(run, job.name, machine_name=mname)
            except Exception as e:                          # noqa: BLE001
                logger.warning(f"notify backup fallÃ³: {e}")

        # Poda del historial al mÃ¡ximo permitido por mÃ¡quina
        try:
            prune_history(machine_id)
        except Exception as e:
            logger.warning(f"prune_history fallÃ³: {e}")
