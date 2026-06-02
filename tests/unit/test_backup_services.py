# tests/unit/test_backup_services.py
"""Tests unitarios para utilidades del módulo de backup que no requieren Flask app."""
import os
from datetime import datetime
from unittest.mock import patch, MagicMock
import pytest

os.environ.setdefault('SECRET_KEY', 'test_secret')
os.environ.setdefault('ADMIN_PASSWORD', 'Admin12345678!')
os.environ.setdefault('FIELD_ENCRYPTION_KEY', 'test_field_encryption_key_32bytes!!')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from modules.backup.services import compute_next_run
from utils.validators import (
    validate_id, validate_enum, validate_schedule_time,
    ALLOWED_DESTINATION_TYPES, ALLOWED_JOB_SCHEDULES,
)


class TestComputeNextRun:
    def test_daily_misma_hora_aun_no_pasada(self):
        # Si ahora son las 10:00 y schedule_time es 23:00 → hoy mismo
        now = datetime(2026, 5, 8, 10, 0, 0)
        nxt = compute_next_run('daily', '23:00', now=now)
        assert nxt == datetime(2026, 5, 8, 23, 0, 0)

    def test_daily_hora_ya_pasada_va_a_manana(self):
        now = datetime(2026, 5, 8, 23, 30, 0)
        nxt = compute_next_run('daily', '02:00', now=now)
        assert nxt == datetime(2026, 5, 9, 2, 0, 0)

    def test_weekly_lanza_lunes(self):
        # 2026-05-08 es viernes; el lunes siguiente es 2026-05-11
        now = datetime(2026, 5, 8, 10, 0, 0)
        nxt = compute_next_run('weekly', '02:00', now=now)
        assert nxt.weekday() == 0
        assert nxt == datetime(2026, 5, 11, 2, 0, 0)

    def test_monthly_dia_1_mes_siguiente(self):
        now = datetime(2026, 5, 8, 10, 0, 0)
        nxt = compute_next_run('monthly', '02:00', now=now)
        assert nxt == datetime(2026, 6, 1, 2, 0, 0)

    def test_monthly_diciembre_pasa_a_enero_siguiente_anio(self):
        now = datetime(2026, 12, 15, 10, 0, 0)
        nxt = compute_next_run('monthly', '02:00', now=now)
        assert nxt == datetime(2027, 1, 1, 2, 0, 0)

    def test_manual_devuelve_none(self):
        assert compute_next_run('manual', '02:00') is None


class TestValidators:
    def test_validate_id_ok(self):
        assert validate_id(5) == 5
        assert validate_id('42') == 42

    def test_validate_id_negativo(self):
        import pytest
        with pytest.raises(ValueError):
            validate_id(-1)

    def test_validate_id_no_numero(self):
        import pytest
        with pytest.raises(ValueError):
            validate_id('foo')

    def test_destination_types_completos(self):
        assert validate_enum('local', ALLOWED_DESTINATION_TYPES, 't') == 'local'
        assert validate_enum('network', ALLOWED_DESTINATION_TYPES, 't') == 'network'

    def test_job_schedules_incluyen_manual(self):
        assert 'manual' in ALLOWED_JOB_SCHEDULES
        assert 'daily' in ALLOWED_JOB_SCHEDULES

    def test_schedule_time(self):
        assert validate_schedule_time('02:00') == '02:00'
        assert validate_schedule_time('23:59') == '23:59'

    def test_schedule_time_invalido(self):
        import pytest
        with pytest.raises(ValueError):
            validate_schedule_time('25:00')
        with pytest.raises(ValueError):
            validate_schedule_time('abc')


# ─── _parse_iso_dt ────────────────────────────────────────────────────────────

class TestParseIsoDt:
    def test_t_separator_format(self):
        from modules.backup.services import _parse_iso_dt
        assert _parse_iso_dt('2026-05-18T14:30:00') == datetime(2026, 5, 18, 14, 30, 0)

    def test_space_separator_format(self):
        from modules.backup.services import _parse_iso_dt
        assert _parse_iso_dt('2026-05-18 14:30:00') == datetime(2026, 5, 18, 14, 30, 0)

    def test_none_returns_none(self):
        from modules.backup.services import _parse_iso_dt
        assert _parse_iso_dt(None) is None

    def test_empty_returns_none(self):
        from modules.backup.services import _parse_iso_dt
        assert _parse_iso_dt('') is None

    def test_invalid_returns_none(self):
        from modules.backup.services import _parse_iso_dt
        assert _parse_iso_dt('not-a-date') is None


# ─── unschedule_job_in_ps con job manual ──────────────────────────────────────

class TestUnscheduleJobInPs:
    @patch('modules.backup.services.resolve_and_send')
    def test_no_short_name_returns_silently(self, mock_send):
        from modules.backup.services import unschedule_job_in_ps
        job = MagicMock()
        job.scheduled_task_name = 'GestionBackup_'  # short queda vacío
        job.machine_id = 1
        # No debe lanzar
        unschedule_job_in_ps(job)
        mock_send.assert_not_called()

    @patch('modules.backup.services.resolve_and_send', return_value='ok')
    def test_with_task_name_sends_command(self, mock_send):
        from modules.backup.services import unschedule_job_in_ps
        job = MagicMock()
        job.scheduled_task_name = 'GestionBackup_test_job'
        job.machine_id = 1
        unschedule_job_in_ps(job)
        mock_send.assert_called_once()


# ─── schedule_job_in_ps ───────────────────────────────────────────────────────

class TestScheduleJobInPs:
    def test_manual_returns_empty(self):
        from modules.backup.services import schedule_job_in_ps
        job = MagicMock()
        job.schedule = 'manual'
        job.enabled = True
        assert schedule_job_in_ps(job) == ''

    def test_disabled_returns_empty(self):
        from modules.backup.services import schedule_job_in_ps
        job = MagicMock()
        job.schedule = 'daily'
        job.enabled = False
        assert schedule_job_in_ps(job) == ''


# ─── _create_run_from_entry ────────────────────────────────────────────────────

class TestCreateRunFromEntry:
    @patch('modules.backup.services.db')
    def test_default_status_completed(self, mock_db):
        from modules.backup.services import _create_run_from_entry
        job = MagicMock()
        job.id = 1
        job.name = 'JobA'
        job.backup_type = 'full'
        entry = {
            'started_at': '2026-05-18T10:00:00',
            'finished_at': '2026-05-18T10:05:00',
            'bytes': '1024',
            'files': '5',
        }
        result = _create_run_from_entry(entry, job, 1, 'json')
        assert result == datetime(2026, 5, 18, 10, 0, 0)
        mock_db.session.add.assert_called_once()

    @patch('modules.backup.services.db')
    def test_invalid_status_defaults_to_completed(self, mock_db):
        from modules.backup.services import _create_run_from_entry
        job = MagicMock()
        job.id = 1
        job.name = 'JobA'
        job.backup_type = 'full'
        entry = {
            'started_at': '2026-05-18T10:00:00',
            'finished_at': '2026-05-18T10:05:00',
            'status': 'weird_status',
            'bytes': '0',
            'files': '0',
        }
        _create_run_from_entry(entry, job, 1, 'log')
        # status invalid → 'completed' por defecto
        added = mock_db.session.add.call_args[0][0]
        assert added.status == 'completed'

    @patch('modules.backup.services.db')
    def test_error_status_preserved(self, mock_db):
        from modules.backup.services import _create_run_from_entry
        job = MagicMock()
        job.id = 1
        job.name = 'JobA'
        job.backup_type = 'full'
        entry = {
            'started_at': '2026-05-18T10:00:00',
            'finished_at': '2026-05-18T10:05:00',
            'status': 'error',
            'error': 'something failed',
            'bytes': '0', 'files': '0',
        }
        _create_run_from_entry(entry, job, 1, 'log')
        added = mock_db.session.add.call_args[0][0]
        assert added.status == 'error'

    @patch('modules.backup.services.db')
    def test_calculates_duration_seconds(self, mock_db):
        from modules.backup.services import _create_run_from_entry
        job = MagicMock()
        job.id = 1
        job.name = 'JobA'
        job.backup_type = 'full'
        entry = {
            'started_at': '2026-05-18T10:00:00',
            'finished_at': '2026-05-18T10:00:30',
            'bytes': '0', 'files': '0',
        }
        _create_run_from_entry(entry, job, 1, 'log')
        added = mock_db.session.add.call_args[0][0]
        assert added.duration_sec == 30.0


# ─── prune_history y start_backup_run (con app) ────────────────────────────────

@pytest.fixture(scope='module')
def app():
    from main import create_app
    app = create_app()
    app.config['TESTING'] = True
    return app


class TestPruneHistory:
    def test_below_threshold_returns_zero(self, app):
        from modules.backup.services import prune_history
        with app.app_context():
            result = prune_history(machine_id=99999, keep=100)
            assert result == 0


class TestStartBackupRun:
    def test_disabled_job_raises(self, app):
        from modules.backup.services import start_backup_run
        job = MagicMock()
        job.enabled = False
        with app.app_context():
            with pytest.raises(ValueError):
                start_backup_run(job, ad_hoc=False)

    @patch('modules.backup.services.threading.Thread')
    @patch('modules.backup.services.db')
    def test_creates_thread_for_enabled_job(self, mock_db, mock_thread, app):
        from modules.backup.services import start_backup_run
        job = MagicMock()
        job.id = 1
        job.machine_id = 1
        job.enabled = True
        job.name = 'JobA'
        job.backup_type = 'full'
        with app.app_context():
            start_backup_run(job, ad_hoc=False)
        mock_thread.assert_called_once()


# ─── import_scheduled_runs ─────────────────────────────────────────────────────

class TestImportScheduledRuns:
    def test_no_jobs_returns_zero(self, app):
        from modules.backup.services import import_scheduled_runs
        with app.app_context():
            # No hay BackupJobs con scheduled_task_name en la BD de test
            result = import_scheduled_runs(machine_id=99999)
            assert result == 0
