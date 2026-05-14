"""Tests de integración — módulo monitorizacion (/api/monitorizacion/*)."""


class TestMonitorizacionUnauthenticated:
    def test_summary_requires_auth(self, module_client):
        assert module_client.get('/api/monitorizacion/summary').status_code == 401

    def test_services_list_requires_auth(self, module_client):
        assert module_client.get('/api/monitorizacion/services').status_code == 401

    def test_create_service_requires_auth(self, module_client):
        assert module_client.post('/api/monitorizacion/services', json={}).status_code == 401


class TestMonitorizacionAuthenticated:
    def test_summary_returns_200(self, module_auth_client):
        resp = module_auth_client.get('/api/monitorizacion/summary')
        assert resp.status_code == 200

    def test_list_services_returns_200(self, module_auth_client):
        resp = module_auth_client.get('/api/monitorizacion/services')
        assert resp.status_code == 200
        data = resp.get_json()
        # El endpoint puede devolver una lista o un dict con clave 'services'
        assert isinstance(data, (list, dict))

    def test_create_service_missing_fields_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/monitorizacion/services', json={})
        assert resp.status_code in (400, 422)

    def test_delete_nonexistent_service(self, module_auth_client):
        resp = module_auth_client.delete('/api/monitorizacion/services/99999')
        assert resp.status_code == 404
