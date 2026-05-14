"""Tests de integración — módulo backup (/api/backup/*).

Cubre los endpoints de destinations, jobs, summary, history y runs
para aumentar la cobertura de modules/backup/routes.py.
"""
from unittest.mock import patch, MagicMock
import pytest


# ─── Fixtures de módulo ────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def machine_id(module_app):
    with module_app.app_context():
        from database.models import Machine
        return Machine.query.first().id


@pytest.fixture(scope='module')
def destination_id(module_auth_client, module_app, machine_id):
    """Crea un destino de backup para los tests."""
    resp = module_auth_client.post('/api/backup/destinations', json={
        'name': 'TestDest',
        'type': 'local',
        'path': 'C:\\Backups\\test',
        'machine_id': machine_id,
    })
    if resp.status_code in (200, 201):
        return resp.get_json().get('id')
    # Si ya existe, obtener el primero
    with module_app.app_context():
        from database.models import BackupDestination
        d = BackupDestination.query.first()
        return d.id if d else None


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


# ─── Destinations ─────────────────────────────────────────────────────────────

class TestBackupDestinations:
    def test_list_destinations_returns_200(self, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/backup/destinations?machine_id={machine_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, (list, dict))

    def test_create_destination_valid(self, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/backup/destinations', json={
            'name': 'LocalBackup',
            'type': 'local',
            'path': 'C:\\Backups',
            'machine_id': machine_id,
        })
        assert resp.status_code in (200, 201)

    def test_create_destination_missing_name(self, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/backup/destinations', json={
            'type': 'local',
            'path': 'C:\\Backups',
            'machine_id': machine_id,
        })
        assert resp.status_code in (400, 422)

    def test_create_destination_invalid_path(self, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/backup/destinations', json={
            'name': 'BadPath',
            'type': 'local',
            'path': 'relative/path',
            'machine_id': machine_id,
        })
        assert resp.status_code in (400, 422)

    def test_delete_nonexistent_destination(self, module_auth_client):
        resp = module_auth_client.delete('/api/backup/destinations/99999')
        assert resp.status_code == 404


# ─── Jobs ────────────────────────────────────────────────────────────────────

class TestBackupJobs:
    def test_list_jobs_returns_200(self, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/backup/jobs?machine_id={machine_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, (list, dict))

    @patch('modules.backup.routes.schedule_job_in_ps', return_value='GestionBackup_test')
    def test_create_job_valid(self, mock_sched, module_auth_client, machine_id, destination_id):
        if destination_id is None:
            pytest.skip('No hay destino disponible')
        resp = module_auth_client.post('/api/backup/jobs', json={
            'name': 'TestJob',
            'source_path': 'C:\\Source',
            'destination_id': destination_id,
            'backup_type': 'full',
            'schedule': 'manual',
            'schedule_time': '02:00',
            'compress': True,
            'verify_after': False,
            'machine_id': machine_id,
        })
        assert resp.status_code in (200, 201)

    def test_create_job_missing_name(self, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/backup/jobs', json={
            'source_path': 'C:\\Source',
            'backup_type': 'full',
            'machine_id': machine_id,
        })
        assert resp.status_code in (400, 422)

    def test_create_job_invalid_backup_type(self, module_auth_client, machine_id, destination_id):
        if destination_id is None:
            pytest.skip('No hay destino disponible')
        resp = module_auth_client.post('/api/backup/jobs', json={
            'name': 'BadTypeJob',
            'source_path': 'C:\\Source',
            'destination_id': destination_id,
            'backup_type': 'invalid_type',
            'machine_id': machine_id,
        })
        assert resp.status_code in (400, 422)

    def test_delete_nonexistent_job(self, module_auth_client):
        resp = module_auth_client.delete('/api/backup/jobs/99999')
        assert resp.status_code == 404

    def test_toggle_nonexistent_job(self, module_auth_client):
        resp = module_auth_client.post('/api/backup/jobs/99999/toggle')
        assert resp.status_code == 404


# ─── Summary ─────────────────────────────────────────────────────────────────

class TestBackupSummary:
    def test_summary_returns_200(self, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/backup/summary?machine_id={machine_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'total_jobs' in data or isinstance(data, dict)


# ─── History ─────────────────────────────────────────────────────────────────

class TestBackupHistory:
    def test_history_returns_200(self, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/backup/history?machine_id={machine_id}')
        assert resp.status_code == 200

    def test_history_pagination(self, module_auth_client, machine_id):
        resp = module_auth_client.get(
            f'/api/backup/history?machine_id={machine_id}&limit=5&offset=0'
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


# ─── Runs ─────────────────────────────────────────────────────────────────────

class TestBackupRuns:
    def test_get_run_nonexistent(self, module_auth_client):
        resp = module_auth_client.get('/api/backup/runs/99999')
        assert resp.status_code == 404
