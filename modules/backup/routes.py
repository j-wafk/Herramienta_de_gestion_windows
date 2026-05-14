# modules/backup/routes.py
from datetime import datetime
from flask import Blueprint, jsonify, request

from database import db
from database.models import (
    Machine, BackupDestination, BackupJob, BackupRun,
)
from modules.auth.decorators import require_role
from utils.audit import log_action
from utils.powershell_client import resolve_and_send
from utils.validators import (
    validate_windows_path, validate_safe_name, validate_enum,
    validate_schedule_time, validate_id,
    ALLOWED_BACKUP_TYPES, ALLOWED_JOB_SCHEDULES,
    ALLOWED_DESTINATION_TYPES, ALLOWED_COMPRESS_LEVELS,
)
from .parsers import (
    parse_backup_output, parse_backup_list_output,
    parse_compression_output, parse_scheduled_tasks_output,
)
from .services import (
    start_backup_run, schedule_job_in_ps, unschedule_job_in_ps,
    compute_next_run, ScheduleError, import_scheduled_runs,
)
import logging

logger = logging.getLogger(__name__)

backup_bp = Blueprint('backup', __name__)


# ── helpers ────────────────────────────────────────────────────────────────────

def _mid():
    """Resuelve machine_id desde query string o JSON body."""
    mid = request.args.get('machine_id')
    if not mid and request.is_json:
        mid = (request.get_json(silent=True) or {}).get('machine_id')
    try:
        return int(mid) if mid else None
    except (TypeError, ValueError):
        return None


def _resolve_machine_or_400():
    mid = _mid()
    if mid is None:
        m = Machine.query.order_by(Machine.id.asc()).first()
        if not m:
            return None, (jsonify({"error": "No hay máquinas registradas"}), 400)
        return m, None
    m = Machine.query.get(mid)
    if not m:
        return None, (jsonify({"error": f"Máquina {mid} no encontrada"}), 404)
    return m, None


def _serialize_job(job: BackupJob):
    """Job + último run resumido."""
    last = (BackupRun.query
            .filter_by(job_id=job.id)
            .order_by(BackupRun.started_at.desc())
            .first())
    d = job.to_dict()
    d['last_run'] = last.to_dict() if last else None
    return d


# ── DESTINOS ───────────────────────────────────────────────────────────────────

@backup_bp.route('/destinations', methods=['GET'])
@require_role('superadmin', 'admin', 'operador')
def list_destinations():
    machine, err = _resolve_machine_or_400()
    if err:
        return err
    items = (BackupDestination.query
             .filter((BackupDestination.machine_id == machine.id) |
                     (BackupDestination.machine_id.is_(None)))
             .order_by(BackupDestination.name.asc())
             .all())
    return jsonify({"destinations": [d.to_dict() for d in items]})


@backup_bp.route('/destinations', methods=['POST'])
@require_role('superadmin', 'admin')
def create_destination():
    data = request.get_json(silent=True) or {}
    machine, err = _resolve_machine_or_400()
    if err:
        return err
    try:
        name = validate_safe_name(data.get('name'), 'name')
        dtype = validate_enum(data.get('type', 'local'), ALLOWED_DESTINATION_TYPES, 'type')
        path = validate_windows_path(data.get('path'), 'path')
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    dest = BackupDestination(
        machine_id=machine.id,
        name=name, type=dtype, path=path, status='unknown',
    )
    db.session.add(dest)
    db.session.commit()
    log_action('backup_destination_create', name,
               f'type={dtype} path={path}', machine_id=machine.id)
    return jsonify({"destination": dest.to_dict()}), 201


@backup_bp.route('/destinations/<int:dest_id>', methods=['PUT'])
@require_role('superadmin', 'admin')
def update_destination(dest_id):
    dest = BackupDestination.query.get_or_404(dest_id)
    data = request.get_json(silent=True) or {}
    try:
        if 'name' in data:
            dest.name = validate_safe_name(data['name'], 'name')
        if 'type' in data:
            dest.type = validate_enum(data['type'], ALLOWED_DESTINATION_TYPES, 'type')
        if 'path' in data:
            dest.path = validate_windows_path(data['path'], 'path')
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    db.session.commit()
    log_action('backup_destination_update', dest.name, machine_id=dest.machine_id)
    return jsonify({"destination": dest.to_dict()})


@backup_bp.route('/destinations/<int:dest_id>', methods=['DELETE'])
@require_role('superadmin', 'admin')
def delete_destination(dest_id):
    dest = BackupDestination.query.get_or_404(dest_id)
    if dest.jobs.count() > 0:
        return jsonify({"error": "El destino está en uso por uno o más trabajos"}), 409
    name = dest.name
    machine_id = dest.machine_id
    db.session.delete(dest)
    db.session.commit()
    log_action('backup_destination_delete', name, machine_id=machine_id)
    return jsonify({"success": True})


@backup_bp.route('/destinations/<int:dest_id>/test', methods=['POST'])
@require_role('superadmin', 'admin', 'operador')
def test_destination(dest_id):
    dest = BackupDestination.query.get_or_404(dest_id)
    if dest.type != 'local':
        dest.status = 'unknown'
        db.session.commit()
        return jsonify({
            "destination": dest.to_dict(),
            "message": f"Tipo '{dest.type}' no soportado en esta versión",
        }), 200
    quoted = '"' + dest.path.replace('"', '') + '"'
    out = resolve_and_send(f'estimate_size {quoted}', dest.machine_id)
    online = 'bytes:' in (out or '').lower() and 'error' not in (out or '').lower()
    dest.status = 'online' if online else 'offline'
    db.session.commit()
    return jsonify({"destination": dest.to_dict(), "output": out})


# ── JOBS ───────────────────────────────────────────────────────────────────────

@backup_bp.route('/jobs', methods=['GET'])
@require_role('superadmin', 'admin', 'operador')
def list_jobs():
    machine, err = _resolve_machine_or_400()
    if err:
        return err
    try:
        import_scheduled_runs(machine.id)
    except Exception as e:
        logger.warning(f"import_scheduled_runs falló: {e}")
    jobs = (BackupJob.query
            .filter_by(machine_id=machine.id)
            .order_by(BackupJob.name.asc())
            .all())
    return jsonify({"jobs": [_serialize_job(j) for j in jobs]})


def _validate_job_payload(data, partial=False):
    """Valida el cuerpo de creación/edición de un job. Devuelve dict normalizado."""
    out = {}
    if 'name' in data or not partial:
        out['name'] = validate_safe_name(data.get('name'), 'name')
    if 'source_path' in data or not partial:
        out['source_path'] = validate_windows_path(data.get('source_path'), 'source_path')
    if 'destination_id' in data or not partial:
        out['destination_id'] = validate_id(data.get('destination_id'), 'destination_id')
    if 'backup_type' in data or not partial:
        out['backup_type'] = validate_enum(
            data.get('backup_type', 'full'), ALLOWED_BACKUP_TYPES, 'backup_type'
        )
    if 'schedule' in data or not partial:
        out['schedule'] = validate_enum(
            data.get('schedule', 'manual'), ALLOWED_JOB_SCHEDULES, 'schedule'
        )
    if 'schedule_time' in data or not partial:
        out['schedule_time'] = validate_schedule_time(data.get('schedule_time', '02:00'))
    for boolean_key in ('compress', 'verify_after', 'encrypt', 'notify', 'enabled'):
        if boolean_key in data:
            out[boolean_key] = bool(data[boolean_key])
    return out


@backup_bp.route('/jobs', methods=['POST'])
@require_role('superadmin', 'admin')
def create_job():
    data = request.get_json(silent=True) or {}
    machine, err = _resolve_machine_or_400()
    if err:
        return err
    try:
        norm = _validate_job_payload(data, partial=False)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    dest = BackupDestination.query.get(norm['destination_id'])
    if not dest:
        return jsonify({"error": "Destino no encontrado"}), 400

    if BackupJob.query.filter_by(machine_id=machine.id, name=norm['name']).first():
        return jsonify({"error": "Ya existe un trabajo con ese nombre en esta máquina"}), 409

    job = BackupJob(
        machine_id=machine.id,
        name=norm['name'],
        source_path=norm['source_path'],
        destination_id=norm['destination_id'],
        backup_type=norm['backup_type'],
        schedule=norm['schedule'],
        schedule_time=norm['schedule_time'],
        compress=norm.get('compress', True),
        verify_after=norm.get('verify_after', True),
        encrypt=norm.get('encrypt', False),
        notify=norm.get('notify', False),
        enabled=norm.get('enabled', True),
    )
    db.session.add(job)
    db.session.commit()

    if job.schedule != 'manual' and job.enabled:
        try:
            task_name = schedule_job_in_ps(job)
            if task_name:
                job.scheduled_task_name = task_name
                job.next_run_at = compute_next_run(job.schedule, job.schedule_time)
                db.session.commit()
        except ScheduleError as e:
            log_action('backup_job_create', job.name,
                       f'src={job.source_path} type={job.backup_type} sched={job.schedule} schedule_failed=1',
                       machine_id=job.machine_id)
            return jsonify({
                "job": _serialize_job(job),
                "warning": f"Trabajo creado pero la tarea programada NO se registró:\n\n{e}",
            }), 201
        except Exception as e:
            return jsonify({
                "job": _serialize_job(job),
                "warning": f"Trabajo creado pero no se pudo programar: {e}",
            }), 201

    log_action('backup_job_create', job.name,
               f'src={job.source_path} type={job.backup_type} sched={job.schedule}',
               machine_id=job.machine_id)
    return jsonify({"job": _serialize_job(job)}), 201


@backup_bp.route('/jobs/<int:job_id>', methods=['PUT'])
@require_role('superadmin', 'admin')
def update_job(job_id):
    job = BackupJob.query.get_or_404(job_id)
    data = request.get_json(silent=True) or {}
    try:
        norm = _validate_job_payload(data, partial=True)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    old_schedule = job.schedule
    for k, v in norm.items():
        setattr(job, k, v)
    db.session.commit()

    # Re-sincronizar con Task Scheduler
    try:
        if old_schedule != 'manual':
            unschedule_job_in_ps(job)
        if job.schedule != 'manual' and job.enabled:
            task_name = schedule_job_in_ps(job)
            job.scheduled_task_name = task_name or None
            job.next_run_at = compute_next_run(job.schedule, job.schedule_time)
        else:
            job.scheduled_task_name = None
            job.next_run_at = None
        db.session.commit()
    except ScheduleError as e:
        job.scheduled_task_name = None
        db.session.commit()
        return jsonify({
            "job": _serialize_job(job),
            "warning": f"Trabajo actualizado pero la tarea programada NO se registró:\n\n{e}",
        })
    except Exception as e:
        return jsonify({
            "job": _serialize_job(job),
            "warning": f"Trabajo actualizado pero la sincronización falló: {e}",
        })

    log_action('backup_job_update', job.name, machine_id=job.machine_id)
    return jsonify({"job": _serialize_job(job)})


@backup_bp.route('/jobs/<int:job_id>', methods=['DELETE'])
@require_role('superadmin', 'admin')
def delete_job(job_id):
    job = BackupJob.query.get_or_404(job_id)
    name = job.name
    machine_id = job.machine_id
    try:
        if job.schedule != 'manual':
            unschedule_job_in_ps(job)
    except Exception:
        pass
    # Las runs (historial) se conservan: rellenar snapshot y huerfanizar.
    runs = BackupRun.query.filter_by(job_id=job.id).all()
    for r in runs:
        if not r.job_name_snapshot:
            r.job_name_snapshot = job.name
        if not r.backup_type_snapshot:
            r.backup_type_snapshot = job.backup_type
        r.job_id = None
    db.session.delete(job)
    db.session.commit()
    log_action('backup_job_delete', name, f'orphaned_runs={len(runs)}',
               machine_id=machine_id)
    return jsonify({"success": True, "orphaned_runs": len(runs)})


@backup_bp.route('/jobs/<int:job_id>/toggle', methods=['POST'])
@require_role('superadmin', 'admin')
def toggle_job(job_id):
    job = BackupJob.query.get_or_404(job_id)
    job.enabled = not job.enabled
    db.session.commit()
    warning = None
    try:
        if job.enabled and job.schedule != 'manual':
            task_name = schedule_job_in_ps(job)
            job.scheduled_task_name = task_name or None
            job.next_run_at = compute_next_run(job.schedule, job.schedule_time)
        elif not job.enabled and job.scheduled_task_name:
            unschedule_job_in_ps(job)
            job.scheduled_task_name = None
            job.next_run_at = None
        db.session.commit()
    except ScheduleError as e:
        job.scheduled_task_name = None
        db.session.commit()
        warning = f"No se pudo registrar la tarea programada:\n\n{e}"
    except Exception:
        pass
    log_action('backup_job_toggle', job.name, f'enabled={job.enabled}',
               machine_id=job.machine_id)
    resp = {"job": _serialize_job(job)}
    if warning:
        resp["warning"] = warning
    return jsonify(resp)


@backup_bp.route('/jobs/<int:job_id>/run', methods=['POST'])
@require_role('superadmin', 'admin', 'operador')
def run_job(job_id):
    job = BackupJob.query.get_or_404(job_id)
    try:
        run = start_backup_run(job)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    log_action('backup_job_run', job.name, f'run_id={run.id}',
               machine_id=job.machine_id)
    return jsonify({"run": run.to_dict()}), 202


@backup_bp.route('/jobs/<int:job_id>/run_scheduled', methods=['POST'])
@require_role('superadmin', 'admin')
def run_scheduled_job(job_id):
    """Fuerza la ejecución de la tarea programada de Windows asociada al job.

    Útil para verificar que la tarea está bien configurada sin esperar a la hora.
    """
    job = BackupJob.query.get_or_404(job_id)
    if not job.scheduled_task_name:
        return jsonify({"error": "Este trabajo no tiene tarea programada"}), 400
    short = job.scheduled_task_name.replace('GestionBackup_', '')
    out = resolve_and_send(f'run_scheduled_backup "{short}"', job.machine_id)
    log_action('backup_scheduled_run', job.name, machine_id=job.machine_id)
    return jsonify({"output": out, "success": 'iniciada' in (out or '').lower()})


@backup_bp.route('/jobs/<int:job_id>/scheduled_log', methods=['GET'])
@require_role('superadmin', 'admin', 'operador')
def get_scheduled_log(job_id):
    """Devuelve las últimas líneas del log de ejecución de la tarea programada."""
    job = BackupJob.query.get_or_404(job_id)
    if not job.scheduled_task_name:
        return jsonify({"error": "Este trabajo no tiene tarea programada"}), 400
    short = job.scheduled_task_name.replace('GestionBackup_', '')
    out = resolve_and_send(f'scheduled_backup_log "{short}"', job.machine_id)
    return jsonify({"output": out})


# ── RUNS ───────────────────────────────────────────────────────────────────────

@backup_bp.route('/runs/<int:run_id>', methods=['GET'])
@require_role('superadmin', 'admin', 'operador')
def get_run(run_id):
    run = BackupRun.query.get_or_404(run_id)
    return jsonify({"run": run.to_dict()})


# ── HISTORIAL ──────────────────────────────────────────────────────────────────

@backup_bp.route('/history', methods=['GET'])
@require_role('superadmin', 'admin', 'operador')
def list_history():
    machine, err = _resolve_machine_or_400()
    if err:
        return err
    # Sincroniza ejecuciones del Task Scheduler (no bloqueante en errores)
    try:
        import_scheduled_runs(machine.id)
    except Exception as e:
        logger.warning(f"import_scheduled_runs falló: {e}")
    try:
        limit = int(request.args.get('limit', 20))
        limit = max(1, min(limit, 200))
    except (TypeError, ValueError):
        limit = 20
    try:
        offset = int(request.args.get('offset', 0))
        offset = max(0, offset)
    except (TypeError, ValueError):
        offset = 0
    q = (request.args.get('q') or '').strip()

    query = BackupRun.query.filter(BackupRun.machine_id == machine.id)
    if q:
        like = f'%{q}%'
        query = query.outerjoin(BackupJob, BackupRun.job_id == BackupJob.id).filter(
            db.or_(
                BackupRun.backup_full_name.ilike(like),
                BackupRun.backup_path.ilike(like),
                BackupRun.status.ilike(like),
                BackupRun.error.ilike(like),
                BackupJob.name.ilike(like),
            )
        )

    total = query.count()
    runs = (query
            .order_by(BackupRun.started_at.desc())
            .limit(limit)
            .offset(offset)
            .all())
    return jsonify({
        "history": [r.to_dict() for r in runs],
        "total":  total,
        "limit":  limit,
        "offset": offset,
        "q":      q,
    })


@backup_bp.route('/history/<int:run_id>', methods=['GET'])
@require_role('superadmin', 'admin', 'operador')
def get_history(run_id):
    run = BackupRun.query.get_or_404(run_id)
    return jsonify({"run": run.to_dict()})


@backup_bp.route('/history/<int:run_id>/restore', methods=['POST'])
@require_role('superadmin', 'admin')
def restore_history(run_id):
    run = BackupRun.query.get_or_404(run_id)
    if run.status != 'completed' or not run.backup_path:
        return jsonify({"error": "Sólo se pueden restaurar copias completadas"}), 400
    data = request.get_json(silent=True) or {}
    try:
        restore_path = validate_windows_path(data.get('restore_path'), 'restore_path')
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    overwrite = bool(data.get('overwrite', False))
    cmd = f'restore "{run.backup_path}" "{restore_path}"'
    if overwrite:
        cmd += ' overwrite'
    out = resolve_and_send(cmd, run.machine_id)
    result = parse_backup_output(out)
    log_action('backup_restore', run.backup_path,
               f'dest={restore_path} overwrite={overwrite}',
               machine_id=run.machine_id)
    return jsonify({
        "output": out,
        "result": result,
        "success": result.get('success', False),
    })


@backup_bp.route('/history/<int:run_id>', methods=['DELETE'])
@require_role('superadmin', 'admin')
def delete_history(run_id):
    run = BackupRun.query.get_or_404(run_id)
    delete_disk = bool(request.args.get('delete_disk', '').lower() in ('1', 'true', 'yes'))
    out = None
    if delete_disk and run.backup_path:
        out = resolve_and_send(f'delete_backup "{run.backup_path}"', run.machine_id)
    db.session.delete(run)
    db.session.commit()
    log_action('backup_history_delete', f'run:{run_id}',
               f'disk={delete_disk}', machine_id=run.machine_id)
    return jsonify({"success": True, "output": out})


@backup_bp.route('/history/<int:run_id>/verify', methods=['POST'])
@require_role('superadmin', 'admin', 'operador')
def verify_history(run_id):
    run = BackupRun.query.get_or_404(run_id)
    if not run.backup_path:
        return jsonify({"error": "El registro no tiene ruta de backup asociada"}), 400
    out = resolve_and_send(f'verify_backup "{run.backup_path}"', run.machine_id)
    success = 'verificado' in (out or '').lower() or 'verified' in (out or '').lower()
    return jsonify({"output": out, "success": success})


# ── RESUMEN ────────────────────────────────────────────────────────────────────

@backup_bp.route('/summary', methods=['GET'])
@require_role('superadmin', 'admin', 'operador')
def get_summary():
    machine, err = _resolve_machine_or_400()
    if err:
        return err
    try:
        import_scheduled_runs(machine.id)
    except Exception as e:
        logger.warning(f"import_scheduled_runs falló: {e}")
    total_jobs = BackupJob.query.filter_by(machine_id=machine.id).count()
    last_run = (BackupRun.query
                .filter_by(machine_id=machine.id)
                .order_by(BackupRun.started_at.desc())
                .first())
    has_errors = (BackupRun.query
                  .filter_by(machine_id=machine.id, status='error')
                  .count()) > 0
    space_bytes = (db.session.query(db.func.coalesce(
                       db.func.sum(BackupRun.bytes_done), 0))
                   .filter(BackupRun.machine_id == machine.id,
                           BackupRun.status == 'completed')
                   .scalar()) or 0
    last_dt = last_run.started_at if last_run else None
    days_since = None
    if last_dt:
        delta = datetime.utcnow() - last_dt
        days_since = max(0, delta.days)
    return jsonify({
        "machine_id":    machine.id,
        "total_jobs":    total_jobs,
        "last_backup":   last_dt.isoformat() if last_dt else None,
        "days_since":    days_since,
        "space_used_gb": round(space_bytes / (1024 ** 3), 2),
        "status":        "warning" if has_errors else "ok",
    })


# ── COMPRESIÓN (sigue disponible) ─────────────────────────────────────────────

@backup_bp.route('/compress', methods=['POST'])
@require_role('superadmin', 'admin')
def compress_files():
    data = request.get_json(silent=True) or {}
    try:
        source_path = validate_windows_path(data.get('source_path'), 'source_path')
        output_path = validate_windows_path(data.get('output_path'), 'output_path')
        compression_level = validate_enum(
            data.get('compression_level', 'normal'),
            ALLOWED_COMPRESS_LEVELS, 'compression_level',
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    out = resolve_and_send(
        f'compress "{source_path}" "{output_path}" {compression_level}', _mid()
    )
    return jsonify({"output": out, "result": parse_compression_output(out)})


@backup_bp.route('/decompress', methods=['POST'])
@require_role('superadmin', 'admin')
def decompress_files():
    data = request.get_json(silent=True) or {}
    try:
        archive_path = validate_windows_path(data.get('archive_path'), 'archive_path')
        output_path = validate_windows_path(data.get('output_path'), 'output_path')
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    out = resolve_and_send(
        f'decompress "{archive_path}" "{output_path}"', _mid()
    )
    return jsonify({
        "output": out,
        "success": 'extra' in (out or '').lower(),
    })


# ── PROGRAMADOS (vista directa de Task Scheduler) ─────────────────────────────

@backup_bp.route('/scheduled', methods=['GET'])
@require_role('superadmin', 'admin', 'operador')
def list_scheduled():
    out = resolve_and_send('list_scheduled_backups', _mid())
    return jsonify({"tasks": parse_scheduled_tasks_output(out), "raw": out})


# ── COMPATIBILIDAD: rutas antiguas para no romper el cliente ──────────────────

@backup_bp.route('/list', methods=['GET'])
@require_role('superadmin', 'admin', 'operador')
def list_backups_legacy():
    """Lista cruda de backups en una ruta del filesystem (no usa BD)."""
    try:
        path = validate_windows_path(request.args.get('path'), 'path')
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    out = resolve_and_send(f'list_backups "{path}"', _mid())
    return jsonify({"backups": parse_backup_list_output(out), "backup_path": path})


@backup_bp.route('/status', methods=['GET'])
@require_role('superadmin', 'admin', 'operador')
def get_backup_status():
    out = resolve_and_send('backup_status', _mid())
    return jsonify({"output": out})
