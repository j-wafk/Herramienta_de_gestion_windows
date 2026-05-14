"""Tests de integración — módulo machines (/api/machines/*)."""


class TestMachinesUnauthenticated:
    def test_list_requires_auth(self, module_client):
        assert module_client.get('/api/machines').status_code == 401

    def test_create_requires_auth(self, module_client):
        assert module_client.post('/api/machines', json={}).status_code == 401

    def test_metrics_requires_auth(self, module_client):
        assert module_client.get('/api/machines/1/metrics').status_code == 401


class TestMachinesAuthenticated:
    def test_list_machines_returns_200(self, module_auth_client):
        resp = module_auth_client.get('/api/machines')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1  # "Local" siempre existe

    def test_create_machine_missing_fields_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/machines', json={})
        assert resp.status_code in (400, 422)

    def test_create_machine_valid(self, module_auth_client):
        resp = module_auth_client.post('/api/machines', json={
            'name': 'TestMachine',
            'ip': '192.168.1.200',
            'port': 12345,
        })
        assert resp.status_code in (200, 201)

    def test_delete_nonexistent_machine(self, module_auth_client):
        resp = module_auth_client.delete('/api/machines/99999')
        assert resp.status_code == 404
