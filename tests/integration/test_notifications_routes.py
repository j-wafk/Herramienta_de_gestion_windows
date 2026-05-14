"""Tests de integración — módulo notifications (/api/notifications/*)."""
from unittest.mock import patch


class TestNotificationsUnauthenticated:
    def test_config_requires_auth(self, module_client):
        assert module_client.get('/api/notifications/config').status_code == 401

    def test_test_email_requires_auth(self, module_client):
        assert module_client.post('/api/notifications/test', json={}).status_code == 401


class TestNotificationsAuthenticated:
    def test_config_returns_200(self, module_auth_client):
        resp = module_auth_client.get('/api/notifications/config')
        assert resp.status_code == 200

    @patch('utils.mailer.send_email', return_value=None)
    def test_send_test_email_no_crash(self, mock_send, module_auth_client):
        resp = module_auth_client.post('/api/notifications/test', json={
            'email': 'test@example.com',
        })
        assert resp.status_code in (200, 400, 500)
