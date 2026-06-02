"""Fixtures compartidas para tests de integración.

Estas fixtures son de ámbito módulo: cada archivo de test obtiene su propio
cliente autenticado. Esto evita:
  - Conflicto con el auth_client function-scoped de test_api_endpoints.py
  - Agotamiento del rate limiter cuando muchos tests hacen login en la misma sesión
"""
import pytest


@pytest.fixture(scope='module')
def module_app():
    """App Flask aislada por módulo, con CSRF y rate limiting desactivados para tests."""
    from main import create_app
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['RATELIMIT_ENABLED'] = False
    return app


@pytest.fixture(scope='module')
def module_client(module_app):
    """Cliente sin autenticar, ámbito módulo."""
    return module_app.test_client()


@pytest.fixture(scope='module')
def module_auth_client(module_app):
    """Cliente autenticado como superadmin, ámbito módulo (login único por archivo)."""
    with module_app.test_client() as client:
        resp = client.post('/auth/login', data={
            'username': 'admin',
            'password': 'Admin12345678!',
        }, follow_redirects=False)
        assert resp.status_code == 302, (
            f"Login falló en fixture module_auth_client: "
            f"status={resp.status_code}, body={resp.data[:200]!r}"
        )
        yield client
