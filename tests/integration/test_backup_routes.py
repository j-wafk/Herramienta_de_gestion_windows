"""Tests de integración — módulo backup (/api/backup/*)."""
from unittest.mock import patch, MagicMock
import pytest


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def machine_id(module_app):
    with module_app.app_context():
        from database.models import Machine
        return Machine.query.first().id


@pytest.fixture(scope='module')
def destination_id(module_auth_client, module_app, machine_id):
    """Crea un destino de backup y devuelve su id."""
    resp = module_auth_client.post(
        '/api/backup/destinations',
        json={'name': 'TestDest', 'type': 'local', 'path': 'C:\\Backups\\test',
              'machine_id': machine_id},
    )
    if resp.status_code in (200, 201):
        return resp.get_json()['destination']['id']
    with module_app.app_context():
        from database.models import BackupDestination
        d = BackupDestination.query.first()
        return d.id if d else None


@pytest.fixture
def temp_job(module_auth_client, machine_id, destination_id):
    """Crea un job temporal y lo limpia al final."""
    if destination_id is None:
        yield None
        return
    with patch('modules.backup.routes.schedule_job_in_ps', return_value=''):
        resp = module_auth_client.post('/api/backup/jobs', json={
            'name': f'tempjob_{id(object())}',
            'source_path': 'C:\\Source',
            'destination_id': destination_id,
            'backup_type': 'full',
            'schedule': 'manual',
            'schedule_time': '02:00',
            'machine_id': machine_id,
        })
    job_id = None
    if resp.status_code in (200, 201):
        job_id = resp.get_json()['job']['id']
    yield job_id
    if job_id:
        with patch('modules.backup.routes.unschedule_job_in_ps'):
            module_auth_client.delete(f'/api/backup/jobs/{job_id}')


# ─── Unauthenticated ───────────────────────────────────────────────────────────

class TestBackupUnauthenticated:
    def test_summary_requires_auth(self, module_client):
        assert module_client.get('/api/backup/summary').status_code == 401

    def test_destinations_requires_auth(self, module_client):
        assert module_client.get('/api/backup/destinations').status_code == 401

    def test_jobs_requires_auth(self, module_client):
        assert module_client.get('/api/backup/jobs').status_code == 401

    def test_history_requires_auth(self, module_client):
        assert module_client.get('/api/backup/history').status_code == 401

    def test_runs_requires_auth(self, module_client):
        assert module_client.get('/api/backup/runs/1').status_code == 401


# ─── Destinations ─────────────────────────────────────────────────────────────

class TestBackupDestinations:
    def test_list_returns_200(self, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/backup/destinations?machine_id={machine_id}')
        assert resp.status_code == 200

    def test_list_invalid_machine_id_returns_404(self, module_auth_client):
        resp = module_auth_client.get('/api/backup/destinations?machine_id=99999')
        assert resp.status_code == 404

    def test_create_valid(self, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/backup/destinations', json={
            'name': 'LocalBackupA', 'type': 'local', 'path': 'C:\\BackupsA',
            'machine_id': machine_id,
        })
        assert resp.status_code in (200, 201)

    def test_create_missing_name_returns_400(self, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/backup/destinations', json={
            'type': 'local', 'path': 'C:\\Backups', 'machine_id': machine_id,
        })
        assert resp.status_code == 400

    def test_create_invalid_path_returns_400(self, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/backup/destinations', json={
            'name': 'BadPath', 'type': 'local', 'path': 'relative/path',
            'machine_id': machine_id,
        })
        assert resp.status_code == 400

    def test_create_invalid_type_returns_400(self, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/backup/destinations', json={
            'name': 'BadType', 'type': 'invalid', 'path': 'C:\\X',
            'machine_id': machine_id,
        })
        assert resp.status_code == 400

    def test_update_nonexistent_returns_404(self, module_auth_client):
        resp = module_auth_client.put('/api/backup/destinations/99999',
                                      json={'name': 'X'})
        assert resp.status_code == 404

    def test_update_destination_valid(self, module_auth_client, destination_id):
        if destination_id is None:
            pytest.skip()
        resp = module_auth_client.put(f'/api/backup/destinations/{destination_id}',
                                      json={'name': 'Renamed'})
        assert resp.status_code == 200

    def test_update_destination_invalid_path_returns_400(self, module_auth_client,
                                                         destination_id):
        if destination_id is None:
            pytest.skip()
        resp = module_auth_client.put(f'/api/backup/destinations/{destination_id}',
                                      json={'path': 'invalid/path'})
        assert resp.status_code == 400

    def test_delete_nonexistent_returns_404(self, module_auth_client):
        resp = module_auth_client.delete('/api/backup/destinations/99999')
        assert resp.status_code == 404

    def test_delete_destination_success(self, module_auth_client, machine_id):
        r = module_auth_client.post('/api/backup/destinations', json={
            'name': 'ToDel', 'type': 'local', 'path': 'C:\\DelMe',
            'machine_id': machine_id,
        })
        if r.status_code in (200, 201):
            dest_id = r.get_json()['destination']['id']
            resp = module_auth_client.delete(f'/api/backup/destinations/{dest_id}')
            assert resp.status_code == 200

    @patch('modules.backup.routes.resolve_and_send', return_value='bytes: 1024')
    def test_test_destination_local(self, mock_ps, module_auth_client, destination_id):
        if destination_id is None:
            pytest.skip()
        resp = module_auth_client.post(f'/api/backup/destinations/{destination_id}/test')
        assert resp.status_code == 200

    def test_test_nonexistent_returns_404(self, module_auth_client):
        resp = module_auth_client.post('/api/backup/destinations/99999/test')
        assert resp.status_code == 404


# ─── Jobs ──────────────────────────────────────────────────────────────────────

class TestBackupJobs:
    def test_list_jobs_returns_200(self, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/backup/jobs?machine_id={machine_id}')
        assert resp.status_code == 200

    def test_list_jobs_invalid_machine_returns_404(self, module_auth_client):
        resp = module_auth_client.get('/api/backup/jobs?machine_id=99999')
        assert resp.status_code == 404

    @patch('modules.backup.routes.schedule_job_in_ps', return_value='')
    def test_create_valid(self, mock_sched, module_auth_client, machine_id, destination_id):
        if destination_id is None:
            pytest.skip()
        resp = module_auth_client.post('/api/backup/jobs', json={
            'name': 'TestJobA',
            'source_path': 'C:\\Source',
            'destination_id': destination_id,
            'backup_type': 'full',
            'schedule': 'manual',
            'schedule_time': '02:00',
            'machine_id': machine_id,
        })
        assert resp.status_code in (200, 201)
        job_id = resp.get_json()['job']['id']
        with patch('modules.backup.routes.unschedule_job_in_ps'):
            module_auth_client.delete(f'/api/backup/jobs/{job_id}')

    def test_create_missing_name_returns_400(self, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/backup/jobs', json={
            'source_path': 'C:\\Source',
            'backup_type': 'full',
            'machine_id': machine_id,
        })
        assert resp.status_code == 400

    def test_create_invalid_type_returns_400(self, module_auth_client, machine_id, destination_id):
        if destination_id is None:
            pytest.skip()
        resp = module_auth_client.post('/api/backup/jobs', json={
            'name': 'BadType', 'source_path': 'C:\\X',
            'destination_id': destination_id, 'backup_type': 'invalid',
            'machine_id': machine_id,
        })
        assert resp.status_code == 400

    def test_create_invalid_dest_returns_400(self, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/backup/jobs', json={
            'name': 'NoDest', 'source_path': 'C:\\X',
            'destination_id': 99999, 'backup_type': 'full',
            'machine_id': machine_id,
        })
        assert resp.status_code == 400

    @patch('modules.backup.routes.schedule_job_in_ps', return_value='')
    def test_create_duplicate_returns_409(self, mock_sched, module_auth_client, machine_id, destination_id):
        if destination_id is None:
            pytest.skip()
        r1 = module_auth_client.post('/api/backup/jobs', json={
            'name': 'DupJob', 'source_path': 'C:\\X',
            'destination_id': destination_id, 'backup_type': 'full',
            'schedule': 'manual', 'machine_id': machine_id,
        })
        r2 = module_auth_client.post('/api/backup/jobs', json={
            'name': 'DupJob', 'source_path': 'C:\\Y',
            'destination_id': destination_id, 'backup_type': 'full',
            'schedule': 'manual', 'machine_id': machine_id,
        })
        assert r2.status_code == 409
        if r1.status_code in (200, 201):
            job_id = r1.get_json()['job']['id']
            with patch('modules.backup.routes.unschedule_job_in_ps'):
                module_auth_client.delete(f'/api/backup/jobs/{job_id}')

    @patch('modules.backup.routes.schedule_job_in_ps')
    def test_create_with_schedule_error(self, mock_sched, module_auth_client, machine_id, destination_id):
        if destination_id is None:
            pytest.skip()
        from modules.backup.services import ScheduleError
        mock_sched.side_effect = ScheduleError('error scheduling')
        resp = module_auth_client.post('/api/backup/jobs', json={
            'name': 'SchedErrJob', 'source_path': 'C:\\X',
            'destination_id': destination_id, 'backup_type': 'full',
            'schedule': 'daily', 'machine_id': machine_id,
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert 'warning' in data
        job_id = data['job']['id']
        with patch('modules.backup.routes.unschedule_job_in_ps'):
            module_auth_client.delete(f'/api/backup/jobs/{job_id}')

    def test_update_nonexistent_returns_404(self, module_auth_client):
        resp = module_auth_client.put('/api/backup/jobs/99999', json={'name': 'X'})
        assert resp.status_code == 404

    @patch('modules.backup.routes.unschedule_job_in_ps')
    @patch('modules.backup.routes.schedule_job_in_ps', return_value='')
    def test_update_valid(self, mock_sched, mock_unsched, module_auth_client, temp_job):
        if temp_job is None:
            pytest.skip()
        resp = module_auth_client.put(f'/api/backup/jobs/{temp_job}', json={
            'name': 'RenamedJob',
        })
        assert resp.status_code == 200

    def test_update_invalid_name_returns_400(self, module_auth_client, temp_job):
        if temp_job is None:
            pytest.skip()
        resp = module_auth_client.put(f'/api/backup/jobs/{temp_job}',
                                      json={'name': '!!invalid!!'})
        assert resp.status_code == 400

    def test_delete_nonexistent_returns_404(self, module_auth_client):
        resp = module_auth_client.delete('/api/backup/jobs/99999')
        assert resp.status_code == 404

    @patch('modules.backup.routes.unschedule_job_in_ps')
    def test_toggle_job(self, mock_unsched, module_auth_client, temp_job):
        if temp_job is None:
            pytest.skip()
        resp = module_auth_client.post(f'/api/backup/jobs/{temp_job}/toggle')
        assert resp.status_code == 200

    def test_toggle_nonexistent_returns_404(self, module_auth_client):
        resp = module_auth_client.post('/api/backup/jobs/99999/toggle')
        assert resp.status_code == 404

    @patch('modules.backup.routes.start_backup_run')
    def test_run_job(self, mock_start, module_auth_client, temp_job):
        if temp_job is None:
            pytest.skip()
        mock_run = MagicMock()
        mock_run.id = 1
        mock_run.to_dict.return_value = {'id': 1, 'status': 'running'}
        mock_start.return_value = mock_run
        resp = module_auth_client.post(f'/api/backup/jobs/{temp_job}/run')
        assert resp.status_code == 202

    def test_run_nonexistent_returns_404(self, module_auth_client):
        resp = module_auth_client.post('/api/backup/jobs/99999/run')
        assert resp.status_code == 404

    @patch('modules.backup.routes.start_backup_run', side_effect=ValueError('disabled'))
    def test_run_disabled_returns_400(self, mock_start, module_auth_client, temp_job):
        if temp_job is None:
            pytest.skip()
        resp = module_auth_client.post(f'/api/backup/jobs/{temp_job}/run')
        assert resp.status_code == 400

    def test_run_scheduled_no_task_returns_400(self, module_auth_client, temp_job):
        if temp_job is None:
            pytest.skip()
        # El temp_job tiene schedule='manual', así que no tiene tarea
        resp = module_auth_client.post(f'/api/backup/jobs/{temp_job}/run_scheduled')
        assert resp.status_code == 400

    def test_scheduled_log_no_task_returns_400(self, module_auth_client, temp_job):
        if temp_job is None:
            pytest.skip()
        resp = module_auth_client.get(f'/api/backup/jobs/{temp_job}/scheduled_log')
        assert resp.status_code == 400


# ─── Runs y History ────────────────────────────────────────────────────────────

class TestBackupHistory:
    def test_history_returns_200(self, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/backup/history?machine_id={machine_id}')
        assert resp.status_code == 200

    def test_history_pagination(self, module_auth_client, machine_id):
        resp = module_auth_client.get(
            f'/api/backup/history?machine_id={machine_id}&limit=5&offset=0'
        )
        assert resp.status_code == 200

    def test_history_invalid_pagination_uses_defaults(self, module_auth_client, machine_id):
        resp = module_auth_client.get(
            f'/api/backup/history?machine_id={machine_id}&limit=abc&offset=xyz'
        )
        assert resp.status_code == 200

    def test_history_search(self, module_auth_client, machine_id):
        resp = module_auth_client.get(
            f'/api/backup/history?machine_id={machine_id}&q=test'
        )
        assert resp.status_code == 200

    def test_history_detail_nonexistent(self, module_auth_client):
        resp = module_auth_client.get('/api/backup/history/99999')
        assert resp.status_code == 404

    def test_history_delete_nonexistent(self, module_auth_client):
        resp = module_auth_client.delete('/api/backup/history/99999')
        assert resp.status_code == 404

    def test_history_restore_nonexistent(self, module_auth_client):
        resp = module_auth_client.post('/api/backup/history/99999/restore',
                                       json={'restore_path': 'C:\\R'})
        assert resp.status_code == 404

    def test_history_verify_nonexistent(self, module_auth_client):
        resp = module_auth_client.post('/api/backup/history/99999/verify')
        assert resp.status_code == 404


# ─── Summary ──────────────────────────────────────────────────────────────────

class TestBackupSummary:
    def test_summary_returns_200(self, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/backup/summary?machine_id={machine_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'total_jobs' in data

    def test_summary_invalid_machine_returns_404(self, module_auth_client):
        resp = module_auth_client.get('/api/backup/summary?machine_id=99999')
        assert resp.status_code == 404


# ─── Runs ─────────────────────────────────────────────────────────────────────

class TestBackupRuns:
    def test_get_run_nonexistent(self, module_auth_client):
        resp = module_auth_client.get('/api/backup/runs/99999')
        assert resp.status_code == 404


# ─── Compress / Decompress ────────────────────────────────────────────────────

class TestCompressDecompress:
    @patch('modules.backup.routes.resolve_and_send', return_value='Comprimido OK')
    def test_compress_success(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/backup/compress', json={
            'source_path': 'C:\\Source',
            'output_path': 'C:\\Out\\archive.zip',
            'compression_level': 'normal',
            'machine_id': machine_id,
        })
        assert resp.status_code == 200

    def test_compress_invalid_source_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/backup/compress', json={
            'source_path': 'relative',
            'output_path': 'C:\\Out',
        })
        assert resp.status_code == 400

    def test_compress_invalid_level_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/backup/compress', json={
            'source_path': 'C:\\X', 'output_path': 'C:\\Y',
            'compression_level': 'invalid',
        })
        assert resp.status_code == 400

    @patch('modules.backup.routes.resolve_and_send', return_value='extraído')
    def test_decompress_success(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/backup/decompress', json={
            'archive_path': 'C:\\Archive.zip',
            'output_path': 'C:\\Out',
            'machine_id': machine_id,
        })
        assert resp.status_code == 200

    def test_decompress_invalid_path_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/backup/decompress', json={
            'archive_path': 'rel',
            'output_path': 'C:\\Out',
        })
        assert resp.status_code == 400


# ─── Scheduled y Status ───────────────────────────────────────────────────────

class TestBackupScheduledStatus:
    @patch('modules.backup.routes.resolve_and_send', return_value='')
    def test_scheduled_returns_200(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/backup/scheduled?machine_id={machine_id}')
        assert resp.status_code == 200

    @patch('modules.backup.routes.resolve_and_send', return_value='status output')
    def test_status_returns_200(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/backup/status?machine_id={machine_id}')
        assert resp.status_code == 200

    @patch('modules.backup.routes.resolve_and_send', return_value='')
    def test_list_legacy_returns_200(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(
            f'/api/backup/list?path=C:\\Backups&machine_id={machine_id}'
        )
        assert resp.status_code == 200

    def test_list_legacy_invalid_path_returns_400(self, module_auth_client):
        resp = module_auth_client.get('/api/backup/list?path=relative')
        assert resp.status_code == 400


# ─── helpers (_mid, _resolve_machine_or_400) ──────────────────────────────────

class TestBackupHelpers:
    def test_mid_invalid_returns_none(self, module_app):
        from modules.backup.routes import _mid
        with module_app.test_request_context('/?machine_id=abc'):
            assert _mid() is None

    def test_mid_none_returns_none(self, module_app):
        from modules.backup.routes import _mid
        with module_app.test_request_context('/'):
            assert _mid() is None
