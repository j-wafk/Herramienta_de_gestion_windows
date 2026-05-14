# tests/integration/test_api_endpoints.py
"""
Tests de integración para los endpoints HTTP.

Diseño:
- Reutilizan la fixture `client` definida en `tests/conftest.py`, que se
  apoya en una sola `app` de scope=session. Esto evita que cada clase
  arranque un nuevo proceso con sus pollers, hilos de background y worker
  de mailer (lo que causaba condiciones de carrera y arranques duplicados).
- Cubren rutas que existen en la arquitectura actual:
    · `/health`            → abierto, devuelve JSON.
    · `/api/*`             → protegido, devuelve 401 sin sesión.
    · `/auth/login` (GET)  → sirve el formulario.
- Para tests con sesión usamos `auth_client`, que hace login con el
  superadmin creado durante el bootstrap (`_ensure_superadmin`).
"""
import json
from unittest.mock import patch

import pytest


# ── Tests sin autenticación ────────────────────────────────────────────────

class TestHealthEndpoint:
    """`/health` está fuera del guard de autenticación."""

    def test_health_check_success(self, client):
        response = client.get('/health')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'ok'

    def test_health_check_returns_json(self, client):
        response = client.get('/health')
        # Talisman puede añadir charset; comprobamos prefijo MIME.
        assert response.content_type.startswith('application/json')


class TestProtectedEndpointsRequireAuth:
    """Sin sesión, las rutas `/api/...` devuelven 401 (JSON)."""

    @pytest.mark.parametrize('path', [
        '/api/system',
        '/api/rendimiento/system',
        '/api/rendimiento/cpu',
        '/api/particiones/disks',
        '/api/red/adapters',
    ])
    def test_get_unauthenticated_returns_401(self, client, path):
        response = client.get(path)
        assert response.status_code == 401, (
            f"{path} devolvió {response.status_code} (se esperaba 401)"
        )

    def test_post_command_unauthenticated_returns_401(self, client):
        response = client.post('/api/command', json={'command': 'cpu'})
        assert response.status_code == 401


class TestLoginPage:
    """El formulario de login debe servirse sin sesión previa."""

    def test_login_page_renders(self, client):
        response = client.get('/auth/login')
        assert response.status_code == 200
        # Comprobar que contiene un formulario.
        assert b'<form' in response.data


# ── Tests autenticados ─────────────────────────────────────────────────────

@pytest.fixture
def auth_client(client):
    """Cliente con sesión iniciada como superadmin (admin / admin12345678).

    Las credenciales se fijan en `tests/conftest.py` mediante variables de
    entorno y `_ensure_superadmin` las usa al crear la cuenta inicial.
    """
    response = client.post('/auth/login', data={
        'username': 'admin',
        'password': 'admin12345678',
    }, follow_redirects=False)
    # 302 = redirect tras login OK; 200 = login renderizado con error.
    assert response.status_code == 302, (
        f"Login falló: status={response.status_code}, "
        f"body={response.data[:200]!r}"
    )
    return client


class TestSystemEndpointAuthenticated:
    """`/api/system` (compatibility blueprint) sin machine_id devuelve los
    datos cacheados por `current_app.cache_manager.get_all_system_data()`.
    """

    def test_system_endpoint_uses_cache_manager(self, auth_client, app):
        mock_payload = {
            'cpu':    {'value': 45.5, 'history': [40, 42, 45, 45.5]},
            'memory': {'value': 60.2, 'history': [55, 58, 60, 60.2]},
            'disk':   {'used': 35.5, 'free': 64.5},
        }
        with patch.object(app.cache_manager, 'get_all_system_data',
                          return_value=mock_payload) as mock_get:
            response = auth_client.get('/api/system')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data == mock_payload
        mock_get.assert_called_once()


class TestCommandEndpointAuthenticated:
    """`/api/command` (compatibility) requiere admin/superadmin y aplica
    una allowlist de comandos para evitar ejecución arbitraria."""

    @patch('compatibility.send_command_to_powershell')
    def test_execute_allowed_command(self, mock_ps, auth_client):
        mock_ps.return_value = "Command output"
        response = auth_client.post('/api/command', json={'command': 'cpu'})
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['output'] == 'Command output'

    def test_execute_disallowed_command_returns_403(self, auth_client):
        response = auth_client.post('/api/command',
                                    json={'command': 'rm -rf /'})
        assert response.status_code == 403

    def test_execute_command_missing_data_returns_400(self, auth_client):
        response = auth_client.post('/api/command', json={})
        assert response.status_code == 400


# ── Manejo de errores ──────────────────────────────────────────────────────

class TestErrorHandling:
    def test_404_on_nonexistent_api_endpoint(self, client):
        # Sin sesión, el guard intercepta antes y devuelve 401 para /api/*.
        # Por eso aceptamos 401 o 404 (según orden de los before_request).
        response = client.get('/api/nonexistent_endpoint_xyz')
        assert response.status_code in (401, 404)

    def test_html_page_unauthenticated_redirects_to_login(self, client):
        response = client.get('/pagina_inexistente_xyz', follow_redirects=False)
        # Sin sesión, las rutas HTML redirigen al login (302).
        assert response.status_code == 302
        assert '/auth/login' in response.headers.get('Location', '')


# ── Headers de seguridad ───────────────────────────────────────────────────

class TestSecurityHeaders:
    """Confirmamos que Flask-Talisman aplica los headers configurados."""

    def test_x_frame_options_deny(self, client):
        response = client.get('/health')
        assert response.headers.get('X-Frame-Options') == 'DENY'

    def test_x_content_type_options_nosniff(self, client):
        response = client.get('/health')
        assert response.headers.get('X-Content-Type-Options') == 'nosniff'

    def test_referrer_policy_present(self, client):
        response = client.get('/health')
        assert response.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'
