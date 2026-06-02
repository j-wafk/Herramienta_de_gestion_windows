"""Tests de integración — módulo monitorizacion (/api/monitorizacion/*)."""
from unittest.mock import patch
import pytest


# ─── Fixtures helpers ──────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def machine_id(module_app):
    with module_app.app_context():
        from database.models import Machine
        return Machine.query.first().id


@pytest.fixture
def created_service(module_auth_client, machine_id, module_app):
    """Crea un servicio temporal y lo devuelve. Lo limpia al final."""
    with patch('modules.monitorizacion.routes.probe_service',
               return_value={'status': 'up', 'latency_ms': 1.5, 'message': 'ok'}):
        resp = module_auth_client.post('/api/monitorizacion/services', json={
            'name': 'TestSvc',
            'ip': '192.168.1.50',
            'port': 80,
            'protocol': 'TCP',
            'machine_id': machine_id,
        })
    svc_id = None
    if resp.status_code == 201:
        svc_id = resp.get_json()['id']
    yield svc_id
    # Cleanup
    if svc_id:
        module_auth_client.delete(f'/api/monitorizacion/services/{svc_id}')


# ─── Unauthenticated ───────────────────────────────────────────────────────────

class TestMonitorizacionUnauthenticated:
    def test_summary_requires_auth(self, module_client):
        assert module_client.get('/api/monitorizacion/summary').status_code == 401

    def test_services_list_requires_auth(self, module_client):
        assert module_client.get('/api/monitorizacion/services').status_code == 401

    def test_create_service_requires_auth(self, module_client):
        assert module_client.post('/api/monitorizacion/services', json={}).status_code == 401

    def test_activity_requires_auth(self, module_client):
        assert module_client.get('/api/monitorizacion/activity').status_code == 401

    def test_machines_post_requires_auth(self, module_client):
        assert module_client.post('/api/monitorizacion/machines', json={}).status_code == 401


# ─── Resumen y listado ─────────────────────────────────────────────────────────

class TestMonitorizacionSummary:
    def test_summary_returns_200(self, module_auth_client):
        resp = module_auth_client.get('/api/monitorizacion/summary')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'machines_total' in data
        assert 'services_total' in data

    def test_list_services_returns_200(self, module_auth_client):
        resp = module_auth_client.get('/api/monitorizacion/services')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'services' in data
        assert isinstance(data['services'], list)

    def test_activity_returns_events(self, module_auth_client):
        resp = module_auth_client.get('/api/monitorizacion/activity')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'events' in data

    def test_activity_with_limit(self, module_auth_client):
        resp = module_auth_client.get('/api/monitorizacion/activity?limit=5')
        assert resp.status_code == 200

    def test_activity_with_invalid_limit_uses_default(self, module_auth_client):
        resp = module_auth_client.get('/api/monitorizacion/activity?limit=abc')
        assert resp.status_code == 200


# ─── Crear servicios ───────────────────────────────────────────────────────────

class TestCreateService:
    def test_create_missing_fields_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/monitorizacion/services', json={})
        assert resp.status_code == 400

    def test_create_missing_name_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/monitorizacion/services', json={
            'ip': '10.0.0.1', 'port': 80, 'protocol': 'TCP',
        })
        assert resp.status_code == 400

    def test_create_missing_ip_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/monitorizacion/services', json={
            'name': 'X', 'port': 80, 'protocol': 'TCP',
        })
        assert resp.status_code == 400

    def test_create_name_too_long_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/monitorizacion/services', json={
            'name': 'x' * 90, 'ip': '10.0.0.1', 'port': 80,
        })
        assert resp.status_code == 400

    def test_create_invalid_ip_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/monitorizacion/services', json={
            'name': 'X', 'ip': '999.999.999.999', 'port': 80,
        })
        assert resp.status_code == 400

    def test_create_invalid_port_string_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/monitorizacion/services', json={
            'name': 'X', 'ip': '10.0.0.1', 'port': 'abc',
        })
        assert resp.status_code == 400

    def test_create_port_out_of_range_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/monitorizacion/services', json={
            'name': 'X', 'ip': '10.0.0.1', 'port': 99999,
        })
        assert resp.status_code == 400

    def test_create_invalid_protocol_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/monitorizacion/services', json={
            'name': 'X', 'ip': '10.0.0.1', 'port': 80, 'protocol': 'FTP',
        })
        assert resp.status_code == 400

    def test_create_invalid_machine_id_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/monitorizacion/services', json={
            'name': 'X', 'ip': '10.0.0.1', 'port': 80, 'machine_id': 'abc',
        })
        assert resp.status_code == 400

    def test_create_nonexistent_machine_id_returns_404(self, module_auth_client):
        resp = module_auth_client.post('/api/monitorizacion/services', json={
            'name': 'X', 'ip': '10.0.0.1', 'port': 80, 'machine_id': 99999,
        })
        assert resp.status_code == 404

    @patch('modules.monitorizacion.routes.probe_service',
           return_value={'status': 'up', 'latency_ms': 2.5, 'message': 'ok'})
    def test_create_with_iis_name_sets_iis_icon(self, mock_probe, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/monitorizacion/services', json={
            'name': 'IIS Web Server',
            'ip': '10.0.0.99',
            'port': 80,
            'machine_id': machine_id,
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['icon_key'] == 'iis'
        # Cleanup
        module_auth_client.delete(f"/api/monitorizacion/services/{data['id']}")

    @patch('modules.monitorizacion.routes.probe_service',
           return_value={'status': 'up', 'latency_ms': 1.0, 'message': 'ok'})
    def test_create_with_sql_name_sets_sql_icon(self, mock_probe, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/monitorizacion/services', json={
            'name': 'SQL Server',
            'ip': '10.0.0.98',
            'port': 1433,
            'machine_id': machine_id,
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['icon_key'] == 'sql'
        module_auth_client.delete(f"/api/monitorizacion/services/{data['id']}")

    @patch('modules.monitorizacion.routes.probe_service',
           return_value={'status': 'up', 'latency_ms': 0.5, 'message': 'ok'})
    def test_create_probe_exception_does_not_fail(self, mock_probe, module_auth_client, machine_id):
        """Si probe_service falla, el servicio se crea igualmente."""
        mock_probe.side_effect = RuntimeError('probe error')
        resp = module_auth_client.post('/api/monitorizacion/services', json={
            'name': 'SSH Server',
            'ip': '10.0.0.97',
            'port': 22,
            'machine_id': machine_id,
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['icon_key'] == 'ssh'
        module_auth_client.delete(f"/api/monitorizacion/services/{data['id']}")


# ─── Update servicios ──────────────────────────────────────────────────────────

class TestUpdateService:
    def test_update_nonexistent_returns_404(self, module_auth_client):
        resp = module_auth_client.put('/api/monitorizacion/services/99999', json={'name': 'X'})
        assert resp.status_code == 404

    @patch('modules.monitorizacion.routes.probe_service',
           return_value={'status': 'down', 'latency_ms': None, 'message': 'fail'})
    def test_update_name(self, mock_probe, module_auth_client, created_service):
        if not created_service:
            pytest.skip('No se pudo crear servicio')
        resp = module_auth_client.put(f'/api/monitorizacion/services/{created_service}',
                                      json={'name': 'RenamedSvc'})
        assert resp.status_code == 200
        assert resp.get_json()['name'] == 'RenamedSvc'

    def test_update_name_empty_returns_400(self, module_auth_client, created_service):
        if not created_service:
            pytest.skip('No se pudo crear servicio')
        resp = module_auth_client.put(f'/api/monitorizacion/services/{created_service}',
                                      json={'name': '   '})
        assert resp.status_code == 400

    def test_update_name_too_long_returns_400(self, module_auth_client, created_service):
        if not created_service:
            pytest.skip('No se pudo crear servicio')
        resp = module_auth_client.put(f'/api/monitorizacion/services/{created_service}',
                                      json={'name': 'x' * 90})
        assert resp.status_code == 400

    def test_update_ip_invalid_returns_400(self, module_auth_client, created_service):
        if not created_service:
            pytest.skip('No se pudo crear servicio')
        resp = module_auth_client.put(f'/api/monitorizacion/services/{created_service}',
                                      json={'ip': 'not-an-ip!!!'})
        assert resp.status_code == 400

    def test_update_port_invalid_returns_400(self, module_auth_client, created_service):
        if not created_service:
            pytest.skip('No se pudo crear servicio')
        resp = module_auth_client.put(f'/api/monitorizacion/services/{created_service}',
                                      json={'port': 'xyz'})
        assert resp.status_code == 400

    def test_update_port_out_of_range_returns_400(self, module_auth_client, created_service):
        if not created_service:
            pytest.skip('No se pudo crear servicio')
        resp = module_auth_client.put(f'/api/monitorizacion/services/{created_service}',
                                      json={'port': 70000})
        assert resp.status_code == 400

    def test_update_protocol_invalid_returns_400(self, module_auth_client, created_service):
        if not created_service:
            pytest.skip('No se pudo crear servicio')
        resp = module_auth_client.put(f'/api/monitorizacion/services/{created_service}',
                                      json={'protocol': 'X'})
        assert resp.status_code == 400

    def test_update_machine_id_invalid_returns_400(self, module_auth_client, created_service):
        if not created_service:
            pytest.skip('No se pudo crear servicio')
        resp = module_auth_client.put(f'/api/monitorizacion/services/{created_service}',
                                      json={'machine_id': 'abc'})
        assert resp.status_code == 400

    def test_update_machine_id_nonexistent_returns_404(self, module_auth_client, created_service):
        if not created_service:
            pytest.skip('No se pudo crear servicio')
        resp = module_auth_client.put(f'/api/monitorizacion/services/{created_service}',
                                      json={'machine_id': 99999})
        assert resp.status_code == 404

    @patch('modules.monitorizacion.routes.probe_service',
           return_value={'status': 'unknown', 'latency_ms': None, 'message': ''})
    def test_update_machine_id_empty_sets_null(self, mock_probe, module_auth_client, created_service):
        if not created_service:
            pytest.skip('No se pudo crear servicio')
        resp = module_auth_client.put(f'/api/monitorizacion/services/{created_service}',
                                      json={'machine_id': ''})
        assert resp.status_code == 200

    def test_update_disable_service(self, module_auth_client, created_service):
        if not created_service:
            pytest.skip('No se pudo crear servicio')
        resp = module_auth_client.put(f'/api/monitorizacion/services/{created_service}',
                                      json={'enabled': False})
        assert resp.status_code == 200
        assert resp.get_json()['enabled'] is False


# ─── Delete y check ──────────────────────────────────────────────────────────

class TestDeleteAndCheckService:
    def test_delete_nonexistent_returns_404(self, module_auth_client):
        resp = module_auth_client.delete('/api/monitorizacion/services/99999')
        assert resp.status_code == 404

    @patch('modules.monitorizacion.routes.probe_service',
           return_value={'status': 'up', 'latency_ms': 1.0, 'message': 'ok'})
    def test_delete_existing(self, mock_probe, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/monitorizacion/services', json={
            'name': 'DelMe', 'ip': '10.0.0.96', 'port': 80, 'machine_id': machine_id,
        })
        svc_id = resp.get_json()['id']
        del_resp = module_auth_client.delete(f'/api/monitorizacion/services/{svc_id}')
        assert del_resp.status_code == 200

    def test_check_nonexistent_returns_404(self, module_auth_client):
        resp = module_auth_client.post('/api/monitorizacion/services/99999/check')
        assert resp.status_code == 404

    @patch('modules.monitorizacion.routes.probe_service',
           return_value={'status': 'up', 'latency_ms': 1.5, 'message': 'ok'})
    def test_check_existing(self, mock_probe, module_auth_client, created_service):
        if not created_service:
            pytest.skip('No se pudo crear servicio')
        resp = module_auth_client.post(f'/api/monitorizacion/services/{created_service}/check')
        assert resp.status_code == 200

    def test_check_disabled_service_returns_400(self, module_auth_client, machine_id):
        # Crear y deshabilitar
        with patch('modules.monitorizacion.routes.probe_service',
                   return_value={'status': 'up', 'latency_ms': 1.0, 'message': ''}):
            resp = module_auth_client.post('/api/monitorizacion/services', json={
                'name': 'Disabled', 'ip': '10.0.0.95', 'port': 22,
                'machine_id': machine_id, 'enabled': False,
            })
        svc_id = resp.get_json()['id']
        check_resp = module_auth_client.post(f'/api/monitorizacion/services/{svc_id}/check')
        assert check_resp.status_code == 400
        module_auth_client.delete(f'/api/monitorizacion/services/{svc_id}')


# ─── Machines en monitorización ────────────────────────────────────────────────

class TestMonitorMachines:
    def test_add_missing_fields_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/monitorizacion/machines', json={})
        assert resp.status_code == 400

    def test_add_invalid_ip_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/monitorizacion/machines', json={
            'name': 'X', 'ip': 'not-an-ip!!!',
        })
        assert resp.status_code == 400

    def test_add_invalid_port_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/monitorizacion/machines', json={
            'name': 'X', 'ip': '10.0.0.1', 'port': 'abc',
        })
        assert resp.status_code == 400

    def test_add_port_out_of_range_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/monitorizacion/machines', json={
            'name': 'X', 'ip': '10.0.0.1', 'port': 99999,
        })
        assert resp.status_code == 400

    def test_add_description_too_long_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/monitorizacion/machines', json={
            'name': 'X', 'ip': '10.0.0.94', 'description': 'd' * 250,
        })
        assert resp.status_code == 400

    def test_add_machine_success(self, module_auth_client):
        resp = module_auth_client.post('/api/monitorizacion/machines', json={
            'name': 'MonitorTest', 'ip': '10.0.0.93', 'port': 12345,
            'description': 'test machine',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        # Cleanup
        module_auth_client.delete(f"/api/monitorizacion/machines/{data['id']}")

    def test_add_duplicate_ip_port_returns_409(self, module_auth_client):
        # Crear primero
        r1 = module_auth_client.post('/api/monitorizacion/machines', json={
            'name': 'Dup1', 'ip': '10.0.0.92', 'port': 12345,
        })
        mid = r1.get_json()['id']
        # Mismo ip:port
        r2 = module_auth_client.post('/api/monitorizacion/machines', json={
            'name': 'Dup2', 'ip': '10.0.0.92', 'port': 12345,
        })
        assert r2.status_code == 409
        module_auth_client.delete(f'/api/monitorizacion/machines/{mid}')

    def test_update_nonexistent_returns_404(self, module_auth_client):
        resp = module_auth_client.put('/api/monitorizacion/machines/99999',
                                      json={'name': 'X'})
        assert resp.status_code == 404

    def test_update_name_empty_returns_400(self, module_auth_client):
        r1 = module_auth_client.post('/api/monitorizacion/machines', json={
            'name': 'UpdTest', 'ip': '10.0.0.91',
        })
        mid = r1.get_json()['id']
        resp = module_auth_client.put(f'/api/monitorizacion/machines/{mid}',
                                      json={'name': '   '})
        assert resp.status_code == 400
        module_auth_client.delete(f'/api/monitorizacion/machines/{mid}')

    def test_update_machine_success(self, module_auth_client):
        r1 = module_auth_client.post('/api/monitorizacion/machines', json={
            'name': 'UpdMe', 'ip': '10.0.0.90',
        })
        mid = r1.get_json()['id']
        resp = module_auth_client.put(f'/api/monitorizacion/machines/{mid}', json={
            'name': 'Updated', 'description': 'new desc',
        })
        assert resp.status_code == 200
        module_auth_client.delete(f'/api/monitorizacion/machines/{mid}')

    def test_update_ip_conflict_returns_409(self, module_auth_client):
        r1 = module_auth_client.post('/api/monitorizacion/machines', json={
            'name': 'A', 'ip': '10.0.0.89', 'port': 12345,
        })
        r2 = module_auth_client.post('/api/monitorizacion/machines', json={
            'name': 'B', 'ip': '10.0.0.88', 'port': 12345,
        })
        mid_a = r1.get_json()['id']
        mid_b = r2.get_json()['id']
        # Intentar cambiar B → ip de A
        resp = module_auth_client.put(f'/api/monitorizacion/machines/{mid_b}', json={
            'ip': '10.0.0.89',
        })
        assert resp.status_code == 409
        module_auth_client.delete(f'/api/monitorizacion/machines/{mid_a}')
        module_auth_client.delete(f'/api/monitorizacion/machines/{mid_b}')

    def test_update_description_too_long_returns_400(self, module_auth_client):
        r1 = module_auth_client.post('/api/monitorizacion/machines', json={
            'name': 'DescTest', 'ip': '10.0.0.87',
        })
        mid = r1.get_json()['id']
        resp = module_auth_client.put(f'/api/monitorizacion/machines/{mid}',
                                      json={'description': 'x' * 250})
        assert resp.status_code == 400
        module_auth_client.delete(f'/api/monitorizacion/machines/{mid}')

    def test_delete_nonexistent_returns_404(self, module_auth_client):
        resp = module_auth_client.delete('/api/monitorizacion/machines/99999')
        assert resp.status_code == 404

    def test_delete_machine_success(self, module_auth_client):
        r1 = module_auth_client.post('/api/monitorizacion/machines', json={
            'name': 'DelMe', 'ip': '10.0.0.86',
        })
        mid = r1.get_json()['id']
        resp = module_auth_client.delete(f'/api/monitorizacion/machines/{mid}')
        assert resp.status_code == 200


# ─── Helpers unitarios ─────────────────────────────────────────────────────────

class TestValidHostHelper:
    def test_valid_ipv4(self):
        from modules.monitorizacion.routes import _valid_host
        assert _valid_host('10.0.0.1') is True
        assert _valid_host('255.255.255.255') is True

    def test_invalid_ipv4_octet(self):
        from modules.monitorizacion.routes import _valid_host
        assert _valid_host('999.0.0.1') is False

    def test_valid_hostname(self):
        from modules.monitorizacion.routes import _valid_host
        assert _valid_host('example.com') is True
        assert _valid_host('sub.example.com') is True

    def test_invalid_empty(self):
        from modules.monitorizacion.routes import _valid_host
        assert _valid_host('') is False
        assert _valid_host(None) is False

    def test_ipv6_simple(self):
        from modules.monitorizacion.routes import _valid_host
        # Acepta IPv6 simplificada (laxo)
        assert _valid_host('::1') is True


class TestIconKeyHelper:
    def test_iis(self):
        from modules.monitorizacion.routes import _icon_key_from_name
        assert _icon_key_from_name('IIS Web') == 'iis'
        assert _icon_key_from_name('webserver') == 'iis'

    def test_sql(self):
        from modules.monitorizacion.routes import _icon_key_from_name
        assert _icon_key_from_name('SQL Server') == 'sql'

    def test_rdp(self):
        from modules.monitorizacion.routes import _icon_key_from_name
        assert _icon_key_from_name('RDP') == 'rdp'

    def test_dns(self):
        from modules.monitorizacion.routes import _icon_key_from_name
        assert _icon_key_from_name('DNS Resolver') == 'dns'

    def test_winrm(self):
        from modules.monitorizacion.routes import _icon_key_from_name
        assert _icon_key_from_name('WinRM') == 'winrm'

    def test_backup(self):
        from modules.monitorizacion.routes import _icon_key_from_name
        assert _icon_key_from_name('Backup Service') == 'backup'

    def test_ssh(self):
        from modules.monitorizacion.routes import _icon_key_from_name
        assert _icon_key_from_name('SSH') == 'ssh'

    def test_api(self):
        from modules.monitorizacion.routes import _icon_key_from_name
        assert _icon_key_from_name('API Gateway') == 'api'

    def test_no_match_returns_empty(self):
        from modules.monitorizacion.routes import _icon_key_from_name
        assert _icon_key_from_name('Custom Service') == ''
        assert _icon_key_from_name(None) == ''
        assert _icon_key_from_name('') == ''
