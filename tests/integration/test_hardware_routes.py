"""Tests de integración — módulo hardware (/api/hardware/*)."""
import json
from unittest.mock import patch
import pytest

_PS_PATH = 'modules.hardware.routes.resolve_and_send'

HW_SNAPSHOT = json.dumps({
    'system': {'hostname': 'PC-TEST', 'os': 'Windows 11'},
    'cpu': {'name': 'Intel Core i7', 'cores': 8},
    'memory': {'total_gb': 16},
    'disks': [], 'gpu': [], 'motherboard': {}, 'devices': [],
})


@pytest.fixture(scope='module')
def machine_id(module_app):
    with module_app.app_context():
        from database.models import Machine
        return Machine.query.first().id


# ─── Unauthenticated ───────────────────────────────────────────────────────────

class TestHardwareUnauthenticated:
    def test_snapshot_requires_auth(self, module_client):
        assert module_client.get('/api/hardware/snapshot').status_code == 401

    def test_system_requires_auth(self, module_client):
        assert module_client.get('/api/hardware/system').status_code == 401

    def test_cpu_requires_auth(self, module_client):
        assert module_client.get('/api/hardware/cpu').status_code == 401

    def test_refresh_requires_auth(self, module_client):
        assert module_client.post('/api/hardware/refresh').status_code == 401

    def test_disks_requires_auth(self, module_client):
        assert module_client.get('/api/hardware/disks').status_code == 401

    def test_gpu_requires_auth(self, module_client):
        assert module_client.get('/api/hardware/gpu').status_code == 401

    def test_motherboard_requires_auth(self, module_client):
        assert module_client.get('/api/hardware/motherboard').status_code == 401

    def test_devices_requires_auth(self, module_client):
        assert module_client.get('/api/hardware/devices').status_code == 401

    def test_export_requires_auth(self, module_client):
        assert module_client.get('/api/hardware/export').status_code == 401


# ─── Snapshot ──────────────────────────────────────────────────────────────────

class TestHardwareSnapshot:
    @patch(_PS_PATH, return_value=HW_SNAPSHOT)
    def test_snapshot_returns_200(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/hardware/snapshot?machine_id={machine_id}')
        assert resp.status_code == 200

    def test_snapshot_invalid_machine_returns_404(self, module_auth_client):
        resp = module_auth_client.get('/api/hardware/snapshot?machine_id=99999')
        assert resp.status_code == 404


# ─── Live endpoints ────────────────────────────────────────────────────────────

class TestHardwareLive:
    @patch(_PS_PATH, return_value='hostname: PC-TEST\nos: Windows 11')
    def test_system_returns_200(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/hardware/system?machine_id={machine_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['hostname'] == 'PC-TEST'

    @patch(_PS_PATH, return_value='hostname: PC-TEST')
    def test_info_alias_returns_200(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/hardware/info?machine_id={machine_id}')
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value='name: Intel Core i7\ncores: 8\nthreads: 16\nsockets: 1')
    def test_cpu_numeric_conversion(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/hardware/cpu?machine_id={machine_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['cores'] == 8

    @patch(_PS_PATH, return_value='name: i7\ncores: invalid_value')
    def test_cpu_invalid_numeric_keeps_string(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/hardware/cpu?machine_id={machine_id}')
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value='total_gb: 16\nused_gb: 8\nfree_gb: 8')
    def test_memory_returns_200(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/hardware/memory?machine_id={machine_id}')
        assert resp.status_code == 200
        assert resp.get_json()['total_gb'] == 16.0

    @patch(_PS_PATH, return_value='total_gb: 16,5\nused_gb: 8,2')
    def test_memory_comma_decimal_converted(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/hardware/memory?machine_id={machine_id}')
        assert resp.status_code == 200
        assert resp.get_json()['total_gb'] == 16.5

    @patch(_PS_PATH, return_value='total_gb: notanumber')
    def test_memory_invalid_keeps_string(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/hardware/memory?machine_id={machine_id}')
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value='total_gb: 8\nused_gb: 4\nfree_gb: 4')
    def test_memory_live(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/hardware/memory/live?machine_id={machine_id}')
        assert resp.status_code == 200

    @patch(_PS_PATH,
           return_value='model|type|status|temperature|capacity_gb|used_gb|used_pct\nSamsung|SSD|OK|35|256|128|50.0')
    def test_disks_returns_200(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/hardware/disks?machine_id={machine_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'disks' in data and len(data['disks']) == 1
        assert data['disks'][0]['capacity_gb'] == 256.0

    @patch(_PS_PATH,
           return_value='model|type|status|temperature|capacity_gb|used_gb|used_pct\nSamsung|SSD|OK|35|invalid|128|50')
    def test_disks_invalid_capacity_defaults_zero(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/hardware/disks?machine_id={machine_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['disks'][0]['capacity_gb'] == 0.0

    @patch(_PS_PATH, return_value='name|vendor\nRTX 3080|NVIDIA')
    def test_gpu_returns_200(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/hardware/gpu?machine_id={machine_id}')
        assert resp.status_code == 200
        assert 'gpus' in resp.get_json()

    @patch(_PS_PATH, return_value='brand: ASUS\nmodel: TUF B550')
    def test_motherboard_returns_200(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/hardware/motherboard?machine_id={machine_id}')
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value='name|class\nUSB Hub|USB')
    def test_devices_returns_200(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/hardware/devices?machine_id={machine_id}')
        assert resp.status_code == 200
        assert 'devices' in resp.get_json()


# ─── Refresh ───────────────────────────────────────────────────────────────────

class TestHardwareRefresh:
    @patch(_PS_PATH, return_value='hostname: PC-TEST')
    def test_refresh_returns_200(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.post(f'/api/hardware/refresh?machine_id={machine_id}')
        assert resp.status_code == 200

    def test_refresh_invalid_machine_returns_404(self, module_auth_client):
        resp = module_auth_client.post('/api/hardware/refresh?machine_id=99999')
        assert resp.status_code == 404


# ─── Export ────────────────────────────────────────────────────────────────────

class TestHardwareExport:
    @patch(_PS_PATH, return_value='hostname: PC-TEST')
    def test_export_returns_json_attachment(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/hardware/export?machine_id={machine_id}')
        assert resp.status_code == 200
        assert 'attachment' in (resp.headers.get('Content-Disposition') or '')


# ─── Helpers de parsing (unit) ─────────────────────────────────────────────────

class TestParseKv:
    def test_basic(self):
        from modules.hardware.routes import _parse_kv
        result = _parse_kv('hostname: PC\nos: Win11')
        assert result == {'hostname': 'PC', 'os': 'Win11'}

    def test_with_bom(self):
        from modules.hardware.routes import _parse_kv
        result = _parse_kv('﻿hostname: PC\nos: Win11')
        assert result['hostname'] == 'PC'

    def test_value_with_colon(self):
        from modules.hardware.routes import _parse_kv
        result = _parse_kv('timestamp: 2026-05-18 14:30:00')
        assert result['timestamp'] == '2026-05-18 14:30:00'

    def test_empty(self):
        from modules.hardware.routes import _parse_kv
        assert _parse_kv('') == {}
        assert _parse_kv(None) == {}

    def test_skips_lines_without_colon(self):
        from modules.hardware.routes import _parse_kv
        result = _parse_kv('valid: ok\nlinea sin colon\notra: linea')
        assert 'valid' in result and 'otra' in result


class TestParsePipe:
    def test_basic(self):
        from modules.hardware.routes import _parse_pipe
        result = _parse_pipe('col1|col2\nval1|val2')
        assert len(result) == 1
        assert result[0]['col1'] == 'val1'

    def test_empty(self):
        from modules.hardware.routes import _parse_pipe
        assert _parse_pipe('') == []
        assert _parse_pipe(None) == []

    def test_skips_malformed_rows(self):
        from modules.hardware.routes import _parse_pipe
        text = 'col1|col2\nval1|val2\nlinea sin pipes\n  '
        result = _parse_pipe(text)
        assert len(result) == 1

    def test_with_bom(self):
        from modules.hardware.routes import _parse_pipe
        result = _parse_pipe('﻿col1|col2\nval1|val2')
        assert len(result) == 1


class TestGetMachineHelper:
    def test_get_machine_with_id(self, module_app, machine_id):
        from modules.hardware.routes import _get_machine
        with module_app.app_context():
            m = _get_machine(machine_id)
            assert m is not None

    def test_get_machine_none_uses_local(self, module_app):
        from modules.hardware.routes import _get_machine
        with module_app.app_context():
            m = _get_machine(None)
            # Puede o no haber una máquina local — solo verifica que no falle
            assert m is None or hasattr(m, 'name')
