"""Tests de integración — módulo rendimiento (/api/rendimiento/*)."""
from unittest.mock import patch

_PS_PATH = 'modules.rendimiento.routes.resolve_and_send'


class TestRendimientoUnauthenticated:
    def test_system_requires_auth(self, module_client):
        assert module_client.get('/api/rendimiento/system').status_code == 401

    def test_cpu_requires_auth(self, module_client):
        assert module_client.get('/api/rendimiento/cpu').status_code == 401

    def test_processes_requires_auth(self, module_client):
        assert module_client.get('/api/rendimiento/processes').status_code == 401


class TestRendimientoAuthenticated:
    @patch(_PS_PATH, return_value='CPU: 45.5%')
    def test_cpu_returns_200(self, mock_ps, module_auth_client, module_app):
        with module_app.app_context():
            from database.models import Machine
            machine = Machine.query.first()
        resp = module_auth_client.get(f'/api/rendimiento/cpu?machine_id={machine.id}')
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value='memoria: 60.3%')
    def test_memory_returns_200(self, mock_ps, module_auth_client, module_app):
        with module_app.app_context():
            from database.models import Machine
            machine = Machine.query.first()
        resp = module_auth_client.get(f'/api/rendimiento/memory?machine_id={machine.id}')
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value='Name|Id|CPU|Memory\nnotepad.exe|1234|5.0|100 MB')
    def test_processes_returns_200(self, mock_ps, module_auth_client, module_app):
        with module_app.app_context():
            from database.models import Machine
            machine = Machine.query.first()
        resp = module_auth_client.get(f'/api/rendimiento/processes?machine_id={machine.id}')
        assert resp.status_code == 200
