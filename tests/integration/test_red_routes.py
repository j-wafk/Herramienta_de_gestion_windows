"""Tests de integración — módulo red (/api/red/*)."""
from unittest.mock import patch
import pytest

_PS_PATH = 'modules.red.routes.resolve_and_send'

ADAPTERS_OUTPUT = (
    'name|type|status|ip|speed\n'
    'Ethernet|Ethernet|Up|192.168.1.10|1000 Mbps\n'
    'Wi-Fi|Wireless|Up|192.168.1.20|300 Mbps'
)
STATS_OUTPUT = (
    'name|rx_mb|tx_mb|rx_packets|tx_packets\n'
    'Ethernet|100|50|1000|800'
)
ACTIVITY_OUTPUT = (
    '2026-05-01 10:00|Info|192.168.1.1|Conexión establecida\n'
    '2026-05-01 11:00|Warn|192.168.1.2|Latencia alta'
)
ALERTS_OUTPUT = (
    'warning|Latencia alta en Wi-Fi|red\n'
    'info|DHCP renovado|ok'
)


@pytest.fixture(scope='module')
def machine_id(module_app):
    with module_app.app_context():
        from database.models import Machine
        return Machine.query.first().id


# ─── Unauthenticated ───────────────────────────────────────────────────────────

class TestRedUnauthenticated:
    def test_adapters_requires_auth(self, module_client):
        assert module_client.get('/api/red/adapters').status_code == 401

    def test_stats_requires_auth(self, module_client):
        assert module_client.get('/api/red/stats').status_code == 401

    def test_activity_requires_auth(self, module_client):
        assert module_client.get('/api/red/activity').status_code == 401

    def test_alerts_requires_auth(self, module_client):
        assert module_client.get('/api/red/alerts').status_code == 401

    def test_tool_requires_auth(self, module_client):
        assert module_client.post('/api/red/tool', json={}).status_code == 401


# ─── Adapters ─────────────────────────────────────────────────────────────────

class TestAdapters:
    @patch(_PS_PATH, return_value=ADAPTERS_OUTPUT)
    def test_list_adapters(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/red/adapters?machine_id={machine_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'adapters' in data
        assert len(data['adapters']) == 2

    def test_adapter_details_no_adapter_returns_empty(self, module_auth_client):
        resp = module_auth_client.get('/api/red/adapter_details')
        assert resp.status_code == 200
        assert resp.get_json() == {}

    def test_adapter_details_invalid_name_returns_400(self, module_auth_client):
        resp = module_auth_client.get('/api/red/adapter_details?adapter=' + 'x' * 100)
        assert resp.status_code == 400

    @patch(_PS_PATH, return_value='name: Ethernet\nip: 192.168.1.10')
    def test_adapter_details_valid(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(
            f'/api/red/adapter_details?adapter=Ethernet&machine_id={machine_id}'
        )
        assert resp.status_code == 200


# ─── Stats / Activity / Alerts ────────────────────────────────────────────────

class TestStatsActivityAlerts:
    @patch(_PS_PATH, return_value=STATS_OUTPUT)
    def test_stats(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/red/stats?machine_id={machine_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'stats' in data

    @patch(_PS_PATH, return_value=ACTIVITY_OUTPUT)
    def test_activity(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/red/activity?machine_id={machine_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'events' in data and len(data['events']) >= 1

    @patch(_PS_PATH, return_value='')
    def test_activity_empty(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/red/activity?machine_id={machine_id}')
        assert resp.status_code == 200
        assert resp.get_json()['events'] == []

    @patch(_PS_PATH, return_value=ALERTS_OUTPUT)
    def test_alerts(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/red/alerts?machine_id={machine_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'alerts' in data


# ─── Tool ─────────────────────────────────────────────────────────────────────

class TestNetworkTool:
    def test_unknown_tool_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/red/tool',
                                       json={'tool': 'inventado', 'target': '8.8.8.8'})
        assert resp.status_code == 400

    @patch(_PS_PATH, return_value='Reply from 8.8.8.8: time=10ms')
    def test_ping_success(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/red/tool', json={
            'tool': 'ping', 'target': '8.8.8.8', 'machine_id': machine_id,
        })
        assert resp.status_code == 200

    def test_ping_invalid_target_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/red/tool', json={
            'tool': 'ping', 'target': '!invalid!',
        })
        assert resp.status_code == 400

    @patch(_PS_PATH, return_value='Traceroute output')
    def test_traceroute_success(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/red/tool', json={
            'tool': 'traceroute', 'target': 'example.com', 'machine_id': machine_id,
        })
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value='IPv4 Address: 192.168.1.10')
    def test_ipconfig(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/red/tool', json={
            'tool': 'ipconfig', 'machine_id': machine_id,
        })
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value='Active connections')
    def test_netstat(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/red/tool', json={
            'tool': 'netstat', 'machine_id': machine_id,
        })
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value='IP renovado')
    def test_release_renew(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/red/tool', json={
            'tool': 'release_renew', 'machine_id': machine_id,
        })
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value='DNS flushed')
    def test_flush_dns(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/red/tool', json={
            'tool': 'flush_dns', 'machine_id': machine_id,
        })
        assert resp.status_code == 200


# ─── Helpers (unit) ───────────────────────────────────────────────────────────

class TestRedHelpers:
    def test_parse_kv_basic(self):
        from modules.red.routes import _parse_kv
        result = _parse_kv('name: Ethernet\nip: 192.168.1.10')
        assert result['name'] == 'Ethernet'

    def test_parse_kv_empty(self):
        from modules.red.routes import _parse_kv
        assert _parse_kv('') == {}
        assert _parse_kv(None) == {}

    def test_parse_pipe_table_basic(self):
        from modules.red.routes import _parse_pipe_table
        headers, rows = _parse_pipe_table('a|b\n1|2')
        assert headers == ['a', 'b']
        assert rows[0]['a'] == '1'

    def test_parse_pipe_table_empty(self):
        from modules.red.routes import _parse_pipe_table
        h, r = _parse_pipe_table('')
        assert h == [] and r == []

    def test_parse_pipe_table_none(self):
        from modules.red.routes import _parse_pipe_table
        h, r = _parse_pipe_table(None)
        assert h == [] and r == []
