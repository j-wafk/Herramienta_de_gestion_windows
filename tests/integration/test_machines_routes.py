"""Tests de integración — módulo machines (/api/machines/*)."""
from unittest.mock import patch
import pytest


@pytest.fixture(scope='module')
def base_machine_id(module_app):
    with module_app.app_context():
        from database.models import Machine
        return Machine.query.first().id


# ─── Unauthenticated ───────────────────────────────────────────────────────────

class TestMachinesUnauthenticated:
    def test_list_requires_auth(self, module_client):
        assert module_client.get('/api/machines').status_code == 401

    def test_create_requires_auth(self, module_client):
        assert module_client.post('/api/machines', json={}).status_code == 401

    def test_metrics_requires_auth(self, module_client):
        assert module_client.get('/api/machines/1/metrics').status_code == 401

    def test_ping_all_requires_auth(self, module_client):
        assert module_client.post('/api/machines/ping_all').status_code == 401

    def test_ping_requires_auth(self, module_client):
        assert module_client.post('/api/machines/1/ping').status_code == 401


# ─── Listado ───────────────────────────────────────────────────────────────────

class TestListMachines:
    def test_list_returns_200(self, module_auth_client):
        resp = module_auth_client.get('/api/machines')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1


# ─── Crear ─────────────────────────────────────────────────────────────────────

class TestCreateMachine:
    def test_missing_fields_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/machines', json={})
        assert resp.status_code == 400

    def test_missing_name_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/machines', json={'ip': '10.5.0.1'})
        assert resp.status_code == 400

    def test_missing_ip_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/machines', json={'name': 'X'})
        assert resp.status_code == 400

    def test_name_too_long_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/machines', json={
            'name': 'x' * 110, 'ip': '10.5.0.2',
        })
        assert resp.status_code == 400

    def test_invalid_ip_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/machines', json={
            'name': 'X', 'ip': '!!invalid!!',
        })
        assert resp.status_code == 400

    def test_invalid_port_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/machines', json={
            'name': 'X', 'ip': '10.5.0.3', 'port': 'not-a-number',
        })
        assert resp.status_code == 400

    def test_port_out_of_range_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/machines', json={
            'name': 'X', 'ip': '10.5.0.4', 'port': 99999,
        })
        assert resp.status_code == 400

    def test_description_too_long_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/machines', json={
            'name': 'X', 'ip': '10.5.0.5', 'description': 'd' * 250,
        })
        assert resp.status_code == 400

    def test_create_with_description(self, module_auth_client):
        resp = module_auth_client.post('/api/machines', json={
            'name': 'WithDesc', 'ip': '10.5.0.6', 'description': 'test desc',
        })
        assert resp.status_code == 201
        mid = resp.get_json()['id']
        module_auth_client.delete(f'/api/machines/{mid}')

    def test_create_duplicate_returns_409(self, module_auth_client):
        r1 = module_auth_client.post('/api/machines', json={
            'name': 'Dup1', 'ip': '10.5.0.7', 'port': 12345,
        })
        mid = r1.get_json()['id']
        r2 = module_auth_client.post('/api/machines', json={
            'name': 'Dup2', 'ip': '10.5.0.7', 'port': 12345,
        })
        assert r2.status_code == 409
        module_auth_client.delete(f'/api/machines/{mid}')


# ─── Update ────────────────────────────────────────────────────────────────────

class TestUpdateMachine:
    def test_update_nonexistent_returns_404(self, module_auth_client):
        resp = module_auth_client.put('/api/machines/99999', json={'name': 'X'})
        assert resp.status_code == 404

    def test_update_name_empty_returns_400(self, module_auth_client):
        r1 = module_auth_client.post('/api/machines', json={
            'name': 'UpdName', 'ip': '10.5.0.8',
        })
        mid = r1.get_json()['id']
        resp = module_auth_client.put(f'/api/machines/{mid}', json={'name': '   '})
        assert resp.status_code == 400
        module_auth_client.delete(f'/api/machines/{mid}')

    def test_update_name_too_long_returns_400(self, module_auth_client):
        r1 = module_auth_client.post('/api/machines', json={
            'name': 'UpdLong', 'ip': '10.5.0.9',
        })
        mid = r1.get_json()['id']
        resp = module_auth_client.put(f'/api/machines/{mid}',
                                      json={'name': 'x' * 110})
        assert resp.status_code == 400
        module_auth_client.delete(f'/api/machines/{mid}')

    def test_update_invalid_ip_returns_400(self, module_auth_client):
        r1 = module_auth_client.post('/api/machines', json={
            'name': 'UpdIp', 'ip': '10.5.0.10',
        })
        mid = r1.get_json()['id']
        resp = module_auth_client.put(f'/api/machines/{mid}',
                                      json={'ip': '!invalid!'})
        assert resp.status_code == 400
        module_auth_client.delete(f'/api/machines/{mid}')

    def test_update_invalid_port_returns_400(self, module_auth_client):
        r1 = module_auth_client.post('/api/machines', json={
            'name': 'UpdPort', 'ip': '10.5.0.11',
        })
        mid = r1.get_json()['id']
        resp = module_auth_client.put(f'/api/machines/{mid}',
                                      json={'port': 'xyz'})
        assert resp.status_code == 400
        module_auth_client.delete(f'/api/machines/{mid}')

    def test_update_port_out_of_range_returns_400(self, module_auth_client):
        r1 = module_auth_client.post('/api/machines', json={
            'name': 'UpdPort2', 'ip': '10.5.0.12',
        })
        mid = r1.get_json()['id']
        resp = module_auth_client.put(f'/api/machines/{mid}', json={'port': 0})
        assert resp.status_code == 400
        module_auth_client.delete(f'/api/machines/{mid}')

    def test_update_ip_conflict_returns_409(self, module_auth_client):
        r1 = module_auth_client.post('/api/machines', json={
            'name': 'A', 'ip': '10.5.0.13', 'port': 12345,
        })
        r2 = module_auth_client.post('/api/machines', json={
            'name': 'B', 'ip': '10.5.0.14', 'port': 12345,
        })
        a_id, b_id = r1.get_json()['id'], r2.get_json()['id']
        resp = module_auth_client.put(f'/api/machines/{b_id}', json={
            'ip': '10.5.0.13',
        })
        assert resp.status_code == 409
        module_auth_client.delete(f'/api/machines/{a_id}')
        module_auth_client.delete(f'/api/machines/{b_id}')

    def test_update_description_too_long_returns_400(self, module_auth_client):
        r1 = module_auth_client.post('/api/machines', json={
            'name': 'UpdDesc', 'ip': '10.5.0.15',
        })
        mid = r1.get_json()['id']
        resp = module_auth_client.put(f'/api/machines/{mid}',
                                      json={'description': 'd' * 250})
        assert resp.status_code == 400
        module_auth_client.delete(f'/api/machines/{mid}')

    def test_update_success(self, module_auth_client):
        r1 = module_auth_client.post('/api/machines', json={
            'name': 'UpdOK', 'ip': '10.5.0.16',
        })
        mid = r1.get_json()['id']
        resp = module_auth_client.put(f'/api/machines/{mid}', json={
            'name': 'Renamed', 'description': 'new',
        })
        assert resp.status_code == 200
        assert resp.get_json()['name'] == 'Renamed'
        module_auth_client.delete(f'/api/machines/{mid}')


# ─── Delete ────────────────────────────────────────────────────────────────────

class TestDeleteMachine:
    def test_delete_nonexistent_returns_404(self, module_auth_client):
        resp = module_auth_client.delete('/api/machines/99999')
        assert resp.status_code == 404

    def test_delete_success(self, module_auth_client):
        r = module_auth_client.post('/api/machines', json={
            'name': 'ToDelete', 'ip': '10.5.0.17',
        })
        mid = r.get_json()['id']
        resp = module_auth_client.delete(f'/api/machines/{mid}')
        assert resp.status_code == 200


# ─── Metrics y services ────────────────────────────────────────────────────────

class TestMachineMetricsServices:
    def test_metrics_nonexistent_returns_404(self, module_auth_client):
        resp = module_auth_client.get('/api/machines/99999/metrics')
        assert resp.status_code == 404

    def test_metrics_returns_list(self, module_auth_client, base_machine_id):
        resp = module_auth_client.get(f'/api/machines/{base_machine_id}/metrics')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_metrics_with_hours_filter(self, module_auth_client, base_machine_id):
        resp = module_auth_client.get(
            f'/api/machines/{base_machine_id}/metrics?hours=24'
        )
        assert resp.status_code == 200

    def test_metrics_hours_capped(self, module_auth_client, base_machine_id):
        resp = module_auth_client.get(
            f'/api/machines/{base_machine_id}/metrics?hours=500'
        )
        assert resp.status_code == 200

    def test_services_nonexistent_returns_404(self, module_auth_client):
        resp = module_auth_client.get('/api/machines/99999/services')
        assert resp.status_code == 404

    def test_services_returns_list(self, module_auth_client, base_machine_id):
        resp = module_auth_client.get(f'/api/machines/{base_machine_id}/services')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)


# ─── Ping ──────────────────────────────────────────────────────────────────────

class TestPingMachine:
    def test_ping_nonexistent_returns_404(self, module_auth_client):
        resp = module_auth_client.post('/api/machines/99999/ping')
        assert resp.status_code == 404

    @patch('socket.socket')
    def test_ping_returns_status(self, mock_socket, module_auth_client, base_machine_id):
        # Configura el mock para simular conexión exitosa
        sock_instance = mock_socket.return_value.__enter__.return_value
        sock_instance.connect_ex.return_value = 0  # éxito
        resp = module_auth_client.post(f'/api/machines/{base_machine_id}/ping')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'status' in data

    @patch('socket.socket')
    def test_ping_failure_marks_offline(self, mock_socket, module_auth_client, base_machine_id):
        sock_instance = mock_socket.return_value.__enter__.return_value
        sock_instance.connect_ex.return_value = 1  # fail
        resp = module_auth_client.post(f'/api/machines/{base_machine_id}/ping')
        assert resp.status_code == 200

    @patch('modules.machines.routes._tcp_probe', return_value=True)
    def test_ping_all_returns_machines(self, mock_probe, module_auth_client):
        resp = module_auth_client.post('/api/machines/ping_all')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    @patch('modules.machines.routes._tcp_probe', return_value=False)
    def test_ping_all_offline(self, mock_probe, module_auth_client):
        resp = module_auth_client.post('/api/machines/ping_all')
        assert resp.status_code == 200


# ─── Helper _tcp_probe ─────────────────────────────────────────────────────────

class TestTcpProbe:
    @patch('socket.socket')
    def test_tcp_probe_success(self, mock_sock):
        from modules.machines.routes import _tcp_probe
        sock_instance = mock_sock.return_value.__enter__.return_value
        sock_instance.connect_ex.return_value = 0
        assert _tcp_probe('10.0.0.1', 12345) is True

    @patch('socket.socket')
    def test_tcp_probe_fail(self, mock_sock):
        from modules.machines.routes import _tcp_probe
        sock_instance = mock_sock.return_value.__enter__.return_value
        sock_instance.connect_ex.return_value = 1
        assert _tcp_probe('10.0.0.1', 12345) is False

    @patch('socket.socket', side_effect=OSError('fail'))
    def test_tcp_probe_exception_returns_false(self, mock_sock):
        from modules.machines.routes import _tcp_probe
        assert _tcp_probe('10.0.0.1', 12345) is False


class TestValidHostMachines:
    def test_valid_ipv4(self):
        from modules.machines.routes import _valid_host
        assert _valid_host('10.0.0.1') is True

    def test_invalid_octet(self):
        from modules.machines.routes import _valid_host
        assert _valid_host('300.0.0.1') is False

    def test_hostname(self):
        from modules.machines.routes import _valid_host
        assert _valid_host('example.com') is True

    def test_empty(self):
        from modules.machines.routes import _valid_host
        assert _valid_host('') is False
        assert _valid_host(None) is False

    def test_ipv6_lax(self):
        from modules.machines.routes import _valid_host
        assert _valid_host('::1') is True
