"""Tests de integración — módulo red (/api/red/*)."""
from unittest.mock import patch

_PS_PATH = 'modules.red.routes.resolve_and_send'

ADAPTERS_OUTPUT = (
    'Name: Ethernet\nIPv4: 192.168.1.10\nIPv6: fe80::1\n'
    'MAC: AA:BB:CC:DD:EE:FF\nStatus: Up\nSpeed: 1000 Mbps\n---\n'
)


class TestRedUnauthenticated:
    def test_adapters_requires_auth(self, module_client):
        assert module_client.get('/api/red/adapters').status_code == 401

    def test_stats_requires_auth(self, module_client):
        assert module_client.get('/api/red/stats').status_code == 401


class TestRedAuthenticated:
    @patch(_PS_PATH, return_value=ADAPTERS_OUTPUT)
    def test_adapters_returns_200(self, mock_ps, module_auth_client, module_app):
        with module_app.app_context():
            from database.models import Machine
            machine = Machine.query.first()
        resp = module_auth_client.get(f'/api/red/adapters?machine_id={machine.id}')
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value='BytesSent: 1024\nBytesReceived: 2048\n')
    def test_stats_returns_200(self, mock_ps, module_auth_client, module_app):
        with module_app.app_context():
            from database.models import Machine
            machine = Machine.query.first()
        resp = module_auth_client.get(f'/api/red/stats?machine_id={machine.id}')
        assert resp.status_code == 200
