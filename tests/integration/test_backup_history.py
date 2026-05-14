# tests/integration/test_backup_history.py
"""
Tests de poda del historial y supervivencia tras borrar el job.
Usan SQLite en memoria; no necesitan PostgreSQL ni el servidor PowerShell.
"""
import os

# IMPORTANTE: configurar el entorno antes de importar `main`/`config`,
# porque Config.DATABASE_URL se lee a nivel de clase al importar.
os.environ.setdefault('SECRET_KEY', 'test_secret')
os.environ.setdefault('ADMIN_PASSWORD', 'admin12345678')
os.environ.setdefault('FIELD_ENCRYPTION_KEY', 'test_field_encryption_key_32bytes!!')
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

import pytest
from datetime import datetime, timedelta


@pytest.fixture(scope='module')
def app():
    from main import create_app
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    return app


@pytest.fixture(autouse=True)
def _isolate_db(app):
    """Limpia las tablas relevantes entre tests."""
    with app.app_context():
        from database import db
        from database.models import BackupRun, BackupJob, BackupDestination
        BackupRun.query.delete()
        BackupJob.query.delete()
        BackupDestination.query.delete()
        db.session.commit()
    yield


def _make_job(machine_id, name='job1'):
    from database import db
    from database.models import BackupDestination, BackupJob
    dest = BackupDestination(machine_id=machine_id, name='d', type='local',
                             path='C:\\X')
    db.session.add(dest)
    db.session.commit()
    job = BackupJob(machine_id=machine_id, name=name, source_path='C:\\Y',
                    destination_id=dest.id, backup_type='full',
                    schedule='manual', schedule_time='02:00')
    db.session.add(job)
    db.session.commit()
    return job


def _seed_runs(machine_id, job_id, n, start_offset_days=0):
    from database import db
    from database.models import BackupRun
    base = datetime.utcnow() - timedelta(days=start_offset_days)
    for i in range(n):
        db.session.add(BackupRun(
            job_id=job_id,
            machine_id=machine_id,
            started_at=base - timedelta(minutes=i),
            status='completed',
            job_name_snapshot='job1',
            backup_type_snapshot='full',
        ))
    db.session.commit()


def test_prune_history_borra_excedente(app):
    from database.models import BackupRun, Machine
    from modules.backup.services import prune_history
    with app.app_context():
        m = Machine.query.first()
        job = _make_job(m.id)
        _seed_runs(m.id, job.id, 120)
        deleted = prune_history(m.id, keep=100)
        assert deleted == 20
        assert BackupRun.query.filter_by(machine_id=m.id).count() == 100


def test_prune_history_no_borra_si_dentro_del_limite(app):
    from database.models import BackupRun, Machine
    from modules.backup.services import prune_history
    with app.app_context():
        m = Machine.query.first()
        job = _make_job(m.id)
        _seed_runs(m.id, job.id, 50)
        assert prune_history(m.id, keep=100) == 0
        assert BackupRun.query.filter_by(machine_id=m.id).count() == 50


def test_prune_history_no_borra_running(app):
    from database import db
    from database.models import BackupRun, Machine
    from modules.backup.services import prune_history
    with app.app_context():
        m = Machine.query.first()
        job = _make_job(m.id)
        _seed_runs(m.id, job.id, 105)
        # Marcar la más antigua como 'running'
        oldest = (BackupRun.query.filter_by(machine_id=m.id)
                  .order_by(BackupRun.started_at.asc()).first())
        oldest.status = 'running'
        db.session.commit()
        prune_history(m.id, keep=100)
        # La 'running' debe sobrevivir aunque esté fuera del top-100
        assert BackupRun.query.filter_by(status='running').count() == 1


def test_borrar_job_conserva_historial_y_anota_snapshot(app):
    from database import db
    from database.models import BackupRun, BackupJob, Machine
    with app.app_context():
        m = Machine.query.first()
        job = _make_job(m.id, name='job_a_borrar')
        _seed_runs(m.id, job.id, 5)
        # Simular el flujo de delete_job sin pasar por HTTP
        runs = BackupRun.query.filter_by(job_id=job.id).all()
        for r in runs:
            r.job_name_snapshot = job.name
            r.backup_type_snapshot = job.backup_type
            r.job_id = None
        db.session.delete(job)
        db.session.commit()

        assert BackupJob.query.count() == 0
        # Las runs siguen ahí, sin job, con snapshot
        orphans = BackupRun.query.filter_by(machine_id=m.id).all()
        assert len(orphans) == 5
        assert all(r.job_id is None for r in orphans)
        assert all(r.job_name_snapshot == 'job_a_borrar' for r in orphans)
        # to_dict marca job_deleted
        d = orphans[0].to_dict()
        assert d['job_deleted'] is True
        assert d['job_name'] == 'job_a_borrar'


def test_to_dict_job_deleted_false_si_job_existe(app):
    from database.models import BackupRun, Machine
    with app.app_context():
        m = Machine.query.first()
        job = _make_job(m.id, name='job_vivo')
        _seed_runs(m.id, job.id, 1)
        run = BackupRun.query.first()
        d = run.to_dict()
        assert d['job_deleted'] is False
        assert d['job_name'] == 'job_vivo'


def test_import_scheduled_runs_log_fallback_y_dedup(app, monkeypatch):
    """Con JSON pop vacío, debe importar desde el log. Y NO duplica si vuelve a invocarse."""
    from database import db
    from database.models import BackupRun, BackupJob, Machine
    import modules.backup.services as svc

    with app.app_context():
        m = Machine.query.first()
        job = _make_job(m.id, name='miJob')
        # Marcar como tarea programada (lo que normalmente hace schedule_job_in_ps)
        job.scheduled_task_name = 'GestionBackup_miJob'
        db.session.commit()

        log_jsonl = (
            '{"task":"GestionBackup_miJob","started_at":"2026-05-08T22:00:00",'
            '"finished_at":"2026-05-08T22:00:05","status":"completed","bytes":1234,'
            '"files":1,"dest":"D:\\\\Backups\\\\backup_20260508_220000.zip","error":null,'
            '"compressed":true}'
        )

        def fake_resolve_and_send(cmd, mid):
            if cmd.startswith('pop_scheduled_runs'):
                return ''  # sin JSON pendiente
            if cmd.startswith('scan_scheduled_runs'):
                return log_jsonl
            return ''

        monkeypatch.setattr(svc, 'resolve_and_send', fake_resolve_and_send)

        n = svc.import_scheduled_runs(m.id)
        assert n == 1
        runs = BackupRun.query.filter_by(job_id=job.id).all()
        assert len(runs) == 1
        r = runs[0]
        assert r.status == 'completed'
        assert r.bytes_done == 1234
        assert r.files_done == 1
        assert 'log' in (r.output or '')

        # Segunda llamada: NO debe duplicar
        n2 = svc.import_scheduled_runs(m.id)
        assert n2 == 0
        assert BackupRun.query.filter_by(job_id=job.id).count() == 1
