"""Tests de integración — módulo hardware (/api/hardware/*)."""
import json
from unittest.mock import patch

_PS_PATH = 'modules.hardware.routes.resolve_and_send'

HW_SNAPSHOT = json.dumps({
    'system': {'hostname': 'PC-TEST', 'os': 'Windows 11'},
    'cpu': {'name': 'Intel Core i7', 'cores': 8},
    'memory': {'total_gb': 16},
    'disks': [], 'gpu': [], 'motherboard': {}, 'devices': [],
})


class TestHardwareUnauthenticated:
    def test_snapshot_requires_auth(self, module_client):
        assert module_client.get('/api/hardware/snapshot').status_code == 401

    def test_system_requires_auth(self, module_client):
        assert module_client.get('/api/hardware/system').status_code == 401

    def test_cpu_requires_auth(self, module_client):
        assert module_client.get('/api/hardware/cpu').status_code == 401


class TestHardwareAuthenticated:
    @patch(_PS_PATH, return_value=HW_SNAPSHOT)
    def test_snapshot_returns_200(self, mock_ps, module_auth_client, module_app):
        with module_app.app_context():
            from database.models import Machine
            machine = Machine.query.first()
        resp = module_auth_client.get(f'/api/hardware/snapshot?machine_id={machine.id}')
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value='cpu_name: Intel Core i7\ncores: 8\nspeed_mhz: 3600')
    def test_cpu_info_returns_200(self, mock_ps, module_auth_client, module_app):
        with module_app.app_context():
            from database.models import Machine
            machine = Machine.query.first()
        resp = module_auth_client.get(f'/api/hardware/cpu?machine_id={machine.id}')
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value='total_gb: 16\nused_gb: 8\nfree_gb: 8')
    def test_memory_info_returns_200(self, mock_ps, module_auth_client, module_app):
        with module_app.app_context():
            from database.models import Machine
            machine = Machine.query.first()
        resp = module_auth_client.get(f'/api/hardware/memory?machine_id={machine.id}')
        assert resp.status_code == 200
