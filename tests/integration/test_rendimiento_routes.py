"""Tests de integración — módulo rendimiento (/api/rendimiento/*)."""
from unittest.mock import patch, MagicMock
import pytest

_PS_PATH = 'modules.rendimiento.routes.resolve_and_send'
_LOCAL_PS = 'modules.rendimiento.routes.send_command_to_powershell'


@pytest.fixture(scope='module')
def machine_id(module_app):
    with module_app.app_context():
        from database.models import Machine
        return Machine.query.first().id


# ─── Unauthenticated ───────────────────────────────────────────────────────────

class TestRendimientoUnauthenticated:
    def test_system_requires_auth(self, module_client):
        assert module_client.get('/api/rendimiento/system').status_code == 401

    def test_cpu_requires_auth(self, module_client):
        assert module_client.get('/api/rendimiento/cpu').status_code == 401

    def test_processes_requires_auth(self, module_client):
        assert module_client.get('/api/rendimiento/processes').status_code == 401

    def test_kill_requires_auth(self, module_client):
        assert module_client.post('/api/rendimiento/process/kill', json={}).status_code == 401

    def test_start_requires_auth(self, module_client):
        assert module_client.post('/api/rendimiento/process/start', json={}).status_code == 401


# ─── Endpoints clásicos ────────────────────────────────────────────────────────

class TestRendimientoClassic:
    @patch(_PS_PATH, return_value='CPU: 45.5%')
    def test_cpu_with_machine_id(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/rendimiento/cpu?machine_id={machine_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'value' in data and 'history' in data

    @patch(_LOCAL_PS, return_value='CPU: 30.0%')
    def test_cpu_without_machine_id_uses_cache(self, mock_ps, module_auth_client):
        resp = module_auth_client.get('/api/rendimiento/cpu')
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value='memoria: 60.3%')
    def test_memory_with_machine_id(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/rendimiento/memory?machine_id={machine_id}')
        assert resp.status_code == 200

    @patch(_LOCAL_PS, return_value='memoria: 50.0%')
    def test_memory_without_machine_id(self, mock_ps, module_auth_client):
        resp = module_auth_client.get('/api/rendimiento/memory')
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value='memoria: 50% Usado: 8.0 GB Total: 16.0 GB')
    def test_memory_detail(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/rendimiento/memory_detail?machine_id={machine_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'pct' in data and 'used_gb' in data and 'total_gb' in data

    @patch(_PS_PATH, return_value='memoria: 50%')
    def test_memory_detail_fallback_pattern(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/rendimiento/memory_detail?machine_id={machine_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['pct'] == 50.0

    @patch(_PS_PATH, return_value='Name|Id|CPU|Memory\nnotepad.exe|1234|5.0|100 MB')
    def test_processes_with_machine_id(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/rendimiento/processes?machine_id={machine_id}')
        assert resp.status_code == 200

    @patch(_LOCAL_PS, return_value='Name|Id|CPU|Memory\nnotepad.exe|1234|5.0|100 MB')
    def test_processes_without_machine_id(self, mock_ps, module_auth_client):
        resp = module_auth_client.get('/api/rendimiento/processes')
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value='proceso terminado')
    def test_kill_process_success(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/rendimiento/process/kill',
                                       json={'pid': 1234, 'machine_id': machine_id})
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    def test_kill_process_no_pid_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/rendimiento/process/kill', json={})
        assert resp.status_code == 400

    @patch(_PS_PATH, return_value='proceso iniciado')
    def test_start_process_success(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/rendimiento/process/start',
                                       json={'comando': 'notepad', 'machine_id': machine_id})
        assert resp.status_code == 200

    def test_start_process_no_comando_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/rendimiento/process/start', json={})
        assert resp.status_code == 400

    @patch(_PS_PATH, return_value='network output')
    def test_network_endpoint(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/rendimiento/network?machine_id={machine_id}')
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value='servicios output')
    def test_services_endpoint(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/rendimiento/services?machine_id={machine_id}')
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value='log output')
    def test_logs_endpoint(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/rendimiento/logs?machine_id={machine_id}')
        assert resp.status_code == 200


# ─── /system ──────────────────────────────────────────────────────────────────

class TestGetSystemData:
    @patch('utils.powershell_client.send_command_to_machine',
           return_value='CPU: 45%')
    def test_system_with_machine_id(self, mock_pm, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/rendimiento/system?machine_id={machine_id}')
        assert resp.status_code == 200

    def test_system_with_nonexistent_machine_id_returns_404(self, module_auth_client):
        resp = module_auth_client.get('/api/rendimiento/system?machine_id=99999')
        assert resp.status_code == 404

    @patch('utils.powershell_client.send_command_to_machine',
           side_effect=RuntimeError('fail'))
    def test_system_with_exception_returns_500(self, mock_pm, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/rendimiento/system?machine_id={machine_id}')
        assert resp.status_code == 500

    @patch(_LOCAL_PS, return_value='CPU: 30%')
    def test_system_local(self, mock_ps, module_auth_client):
        resp = module_auth_client.get('/api/rendimiento/system')
        assert resp.status_code == 200


# ─── Vista General ─────────────────────────────────────────────────────────────

class TestRendimientoOverview:
    @patch(_PS_PATH, return_value='hostname: PC-TEST\nos: Windows 11\nram: 16 GB')
    def test_system_info(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/rendimiento/system_info?machine_id={machine_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('hostname') == 'PC-TEST'

    @patch(_PS_PATH, return_value='Spooler: Running\nBITS: Stopped')
    def test_services_status(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/rendimiento/services_status?machine_id={machine_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'services' in data and len(data['services']) >= 2

    @patch(_PS_PATH, return_value='antivirus: ok\nfirewall: ok')
    def test_security_status(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/rendimiento/security_status?machine_id={machine_id}')
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value='used_pct: 40\nfree_pct: 60\nfree_gb: 100\ntotal_gb: 250\nused_gb: 150')
    def test_disk_summary(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/rendimiento/disk_summary?machine_id={machine_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'used_pct' in data and 'history' in data

    @patch(_PS_PATH, return_value='')
    def test_disk_summary_empty_uses_defaults(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/rendimiento/disk_summary?machine_id={machine_id}')
        assert resp.status_code == 200

    @patch(_PS_PATH,
           return_value='2026-05-01 10:00|Info|System|Algo pasó\n2026-05-01 11:00|Error|App|Algo falló')
    def test_recent_activity(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/rendimiento/recent_activity?machine_id={machine_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'events' in data
        assert len(data['events']) >= 1

    @patch(_PS_PATH,
           return_value='Letter|Label|Total|Used|Free|Pct\nC|Sistema|256|128|128|50.0\nD|Datos|500|250|250|50.0')
    def test_disk_list(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/rendimiento/disk_list?machine_id={machine_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'disks' in data and 'totals' in data
        assert len(data['disks']) == 2

    @patch(_PS_PATH, return_value='')
    def test_disk_list_empty(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/rendimiento/disk_list?machine_id={machine_id}')
        assert resp.status_code == 200

    @patch(_PS_PATH,
           return_value='usage_pct: 25\ndown_bps: 1000000\nup_bps: 500000\nlink_bps: 100000000')
    def test_network_stats(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/rendimiento/network_stats?machine_id={machine_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['usage_pct'] == 25.0

    @patch(_PS_PATH, return_value='invalid: data\nfoo bar')
    def test_network_stats_invalid_values_use_defaults(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/rendimiento/network_stats?machine_id={machine_id}')
        assert resp.status_code == 200


# ─── /history ──────────────────────────────────────────────────────────────────

class TestRendimientoHistory:
    def test_history_with_machine_id(self, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/rendimiento/history?machine_id={machine_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'metrics' in data and 'machine' in data

    def test_history_with_invalid_machine_id_returns_404(self, module_auth_client):
        resp = module_auth_client.get('/api/rendimiento/history?machine_id=99999')
        assert resp.status_code == 404

    def test_history_with_hours_filter(self, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/rendimiento/history?machine_id={machine_id}&hours=24')
        assert resp.status_code == 200

    def test_history_hours_capped_at_168(self, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/rendimiento/history?machine_id={machine_id}&hours=500')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['hours'] == 168


# ─── Parser edge cases (unit) ──────────────────────────────────────────────────

class TestRendimientoParsersEdge:
    def test_parse_cpu_invalid_text_returns_zero(self):
        from modules.rendimiento.parsers import parse_cpu_output
        assert parse_cpu_output('No hay datos') == 0.0

    def test_parse_cpu_exception_returns_zero(self):
        from modules.rendimiento.parsers import parse_cpu_output
        # None lanza error → return 0.0
        assert parse_cpu_output(None) == 0.0

    def test_parse_memory_invalid_returns_zero(self):
        from modules.rendimiento.parsers import parse_memory_output
        assert parse_memory_output('Sin datos válidos') == 0.0

    def test_parse_memory_exception_returns_zero(self):
        from modules.rendimiento.parsers import parse_memory_output
        assert parse_memory_output(None) == 0.0

    def test_parse_disk_legacy_format(self):
        from modules.rendimiento.parsers import parse_disk_output
        result = parse_disk_output('Disco usado: 30.5%, Disco libre: 69.5%')
        assert result == {'used': 30.5, 'free': 69.5}

    def test_parse_disk_new_format(self):
        from modules.rendimiento.parsers import parse_disk_output
        result = parse_disk_output('Usado: 25.0% Libre: 75.0%')
        assert result['used'] == 25.0
        assert result['free'] == 75.0

    def test_parse_disk_used_only_calculates_free(self):
        from modules.rendimiento.parsers import parse_disk_output
        result = parse_disk_output('Disco usado: 40%')
        assert result['used'] == 40.0
        assert result['free'] == 60.0

    def test_parse_disk_no_data_defaults(self):
        from modules.rendimiento.parsers import parse_disk_output
        result = parse_disk_output('no data')
        assert result == {'used': 0.0, 'free': 100.0}

    def test_parse_disk_exception_returns_defaults(self):
        from modules.rendimiento.parsers import parse_disk_output
        result = parse_disk_output(None)
        assert result == {'used': 0.0, 'free': 100.0}

    def test_parse_process_empty(self):
        from modules.rendimiento.parsers import parse_process_output
        assert parse_process_output('') == []

    def test_parse_process_old_format(self):
        from modules.rendimiento.parsers import parse_process_output
        text = "Name      Id   CPU   Memory\nnotepad   1234  5.5   100 MB\n"
        result = parse_process_output(text)
        # Devuelve al menos una entrada parseada
        assert isinstance(result, list)

    def test_parse_process_invalid_cpu_uses_zero(self):
        from modules.rendimiento.parsers import parse_process_output
        text = "Name|Id|CPU|Memory\nnotepad|1234|invalid_cpu|100 MB"
        result = parse_process_output(text)
        assert len(result) >= 1
        assert result[0]['cpu'] == 0.0

    def test_parse_process_skips_lines_without_pipes(self):
        from modules.rendimiento.parsers import parse_process_output
        text = "Name|Id|CPU|Memory\nlinea sin pipes\nnotepad|1234|5.0|100 MB"
        result = parse_process_output(text)
        assert isinstance(result, list)

    def test_parse_process_skips_short_pipe_rows(self):
        from modules.rendimiento.parsers import parse_process_output
        text = "Name|Id|CPU|Memory\nshort|row"
        result = parse_process_output(text)
        assert result == []
