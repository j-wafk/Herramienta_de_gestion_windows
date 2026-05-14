# tests/integration/test_auth_routes.py
"""Tests de integración para el módulo de autenticación.

Cubre: login/logout, protección de rutas por rol, perfil, gestión de usuarios.
Usa SQLite en memoria para no requerir PostgreSQL.
"""
import os
import json

os.environ.setdefault('SECRET_KEY', 'test_secret_auth')
os.environ.setdefault('ADMIN_PASSWORD', 'admin12345678')
os.environ.setdefault('FIELD_ENCRYPTION_KEY', 'test_field_encryption_key_32bytes!!')
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def app():
    from main import create_app
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['RATELIMIT_ENABLED'] = False
    return app


@pytest.fixture(scope='module')
def admin_user_id(app):
    """Devuelve el id del usuario superadmin."""
    with app.app_context():
        from database.models import User
        admin = User.query.filter_by(role='superadmin').first()
        assert admin is not None, "El bootstrap debe crear un superadmin"
        return admin.id


@pytest.fixture(scope='module')
def admin_username(app):
    """Devuelve el nombre del usuario superadmin creado en el bootstrap."""
    with app.app_context():
        from database.models import User
        admin = User.query.filter_by(role='superadmin').first()
        assert admin is not None, "El bootstrap debe crear un superadmin"
        return admin.username


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def logged_client(app, admin_user_id):
    """Cliente con sesión de admin establecida directamente (evita el login HTTP
    para no consumir el rate-limit de /auth/login en la batería de tests)."""
    from datetime import datetime
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess['_user_id'] = str(admin_user_id)
            sess['_fresh'] = True
            sess['_last_active'] = datetime.utcnow().isoformat()
        yield c


# ── Login / Logout ────────────────────────────────────────────────────────────

class TestLoginPage:
    def test_get_login_devuelve_200(self, client):
        resp = client.get('/auth/login')
        assert resp.status_code == 200

    def test_login_correcto_redirige(self, client, admin_username):
        resp = client.post('/auth/login', data={
            'username': admin_username,
            'password': os.environ['ADMIN_PASSWORD'],
        }, follow_redirects=False)
        assert resp.status_code == 302

    def test_login_correcto_redirige_a_index(self, client, admin_username):
        resp = client.post('/auth/login', data={
            'username': admin_username,
            'password': os.environ['ADMIN_PASSWORD'],
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_login_contrasena_incorrecta_no_redirige(self, client, admin_username):
        resp = client.post('/auth/login', data={
            'username': admin_username,
            'password': 'contraseña_INCORRECTA_999',
        }, follow_redirects=False)
        # Permanece en la página de login (200) o redirige a ella (302→200)
        final = client.post('/auth/login', data={
            'username': admin_username,
            'password': 'contraseña_INCORRECTA_999',
        }, follow_redirects=True)
        # Debe mostrar la página de login con el error
        assert final.status_code == 200
        assert b'incorrectos' in final.data.lower()

    def test_login_usuario_inexistente_no_redirige(self, client):
        resp = client.post('/auth/login', data={
            'username': 'usuarioquenexiste',
            'password': 'CualquierPass1!',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b'incorrectos' in resp.data.lower()

    def test_logout_sin_sesion_redirige_a_login(self, client):
        resp = client.get('/auth/logout', follow_redirects=False)
        assert resp.status_code == 302
        assert 'login' in resp.location.lower()

    def test_logout_con_sesion_redirige(self, logged_client):
        resp = logged_client.get('/auth/logout', follow_redirects=False)
        assert resp.status_code == 302


# ── require_role: rutas API sin autenticar → 401 ──────────────────────────────

class TestRequireRoleUnauthenticated:
    def test_api_usuarios_sin_auth_devuelve_401(self, client):
        resp = client.get('/auth/api/usuarios')
        assert resp.status_code == 401
        data = json.loads(resp.data)
        assert 'error' in data

    def test_api_registros_sin_auth_devuelve_401(self, client):
        resp = client.get('/auth/api/registros')
        assert resp.status_code == 401
        data = json.loads(resp.data)
        assert 'error' in data

    def test_api_monitorizacion_sin_auth_devuelve_401(self, client):
        resp = client.get('/api/monitorizacion/services')
        assert resp.status_code == 401

    def test_api_perfil_sin_auth_redirige_o_401(self, client):
        resp = client.get('/auth/api/profile')
        assert resp.status_code in (302, 401)

    def test_page_usuarios_sin_auth_redirige(self, client):
        resp = client.get('/auth/usuarios', follow_redirects=False)
        assert resp.status_code == 302
        assert 'login' in resp.location.lower()


# ── Rutas protegidas con sesión admin ─────────────────────────────────────────

class TestAuthenticatedRoutes:
    def test_api_usuarios_con_auth_devuelve_200(self, logged_client):
        resp = logged_client.get('/auth/api/usuarios')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, list)

    def test_api_usuarios_incluye_admin(self, logged_client, admin_username):
        resp = logged_client.get('/auth/api/usuarios')
        data = json.loads(resp.data)
        usernames = [u['username'] for u in data]
        assert admin_username in usernames

    def test_api_perfil_con_auth_devuelve_datos(self, logged_client, admin_username):
        resp = logged_client.get('/auth/api/profile')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['username'] == admin_username

    def test_api_registros_con_auth_devuelve_200(self, logged_client):
        resp = logged_client.get('/auth/api/registros')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'entries' in data
        assert 'total' in data


# ── Gestión de usuarios (CRUD) ────────────────────────────────────────────────

class TestUserCRUD:
    def test_crear_usuario_valido(self, app, logged_client):
        resp = logged_client.post('/auth/api/usuarios', json={
            'username': 'testusr1',
            'password': 'TestPass@1234',
            'role': 'operador',
        })
        assert resp.status_code == 201
        data = json.loads(resp.data)
        assert data['username'] == 'testusr1'
        assert data['role'] == 'operador'
        # Limpieza
        with app.app_context():
            from database import db
            from database.models import User
            u = User.query.filter_by(username='testusr1').first()
            if u:
                db.session.delete(u)
                db.session.commit()

    def test_crear_usuario_sin_password_devuelve_400(self, logged_client):
        resp = logged_client.post('/auth/api/usuarios', json={
            'username': 'sinpassword',
            'role': 'operador',
        })
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert 'error' in data

    def test_crear_usuario_duplicado_devuelve_409(self, logged_client, admin_username):
        resp = logged_client.post('/auth/api/usuarios', json={
            'username': admin_username,
            'password': 'TestPass@1234',
            'role': 'operador',
        })
        assert resp.status_code == 409
        data = json.loads(resp.data)
        assert 'error' in data

    def test_crear_usuario_rol_invalido_devuelve_400(self, logged_client):
        resp = logged_client.post('/auth/api/usuarios', json={
            'username': 'new_user_rol',
            'password': 'TestPass@1234',
            'role': 'superusuario_inventado',
        })
        assert resp.status_code == 400

    def test_crear_usuario_contrasena_debil_devuelve_400(self, logged_client):
        resp = logged_client.post('/auth/api/usuarios', json={
            'username': 'weakpwduser',
            'password': '12345',
            'role': 'operador',
        })
        assert resp.status_code == 400


# ── Actualización de perfil ───────────────────────────────────────────────────

class TestProfileUpdate:
    def test_actualizar_idioma(self, logged_client):
        resp = logged_client.post('/auth/api/profile/update', json={
            'language': 'en',
        })
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['language'] == 'en'
        # Restaurar
        logged_client.post('/auth/api/profile/update', json={'language': 'es'})

    def test_actualizar_tema(self, logged_client):
        resp = logged_client.post('/auth/api/profile/update', json={
            'theme': 'dark',
        })
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['theme'] == 'dark'
        logged_client.post('/auth/api/profile/update', json={'theme': 'light'})

    def test_actualizar_idioma_invalido_devuelve_400(self, logged_client):
        resp = logged_client.post('/auth/api/profile/update', json={
            'language': 'xx',
        })
        assert resp.status_code == 400

    def test_actualizar_sin_campos_devuelve_400(self, logged_client):
        resp = logged_client.post('/auth/api/profile/update', json={})
        assert resp.status_code == 400

    def test_actualizar_avatar_color_valido(self, logged_client):
        resp = logged_client.post('/auth/api/profile/update', json={
            'avatar_color': '#FF5733',
        })
        assert resp.status_code == 200

    def test_actualizar_avatar_color_invalido_devuelve_400(self, logged_client):
        resp = logged_client.post('/auth/api/profile/update', json={
            'avatar_color': 'rojo',
        })
        assert resp.status_code == 400


# ── Cambio de contraseña ──────────────────────────────────────────────────────

class TestChangePassword:
    def test_contrasena_actual_incorrecta_devuelve_400(self, logged_client):
        resp = logged_client.post('/auth/api/profile/password', json={
            'current_password': 'INCORRECTA_1234@',
            'new_password': 'NuevaSegura@1234',
            'confirm_password': 'NuevaSegura@1234',
        })
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert 'incorrecta' in data['error'].lower()

    def test_contrasenas_no_coinciden_devuelve_400(self, logged_client):
        resp = logged_client.post('/auth/api/profile/password', json={
            'current_password': os.environ['ADMIN_PASSWORD'],
            'new_password': 'NuevaSegura@1234',
            'confirm_password': 'OtraDistinta@1234',
        })
        assert resp.status_code == 400

    def test_nueva_contrasena_debil_devuelve_400(self, logged_client):
        resp = logged_client.post('/auth/api/profile/password', json={
            'current_password': os.environ['ADMIN_PASSWORD'],
            'new_password': 'debil',
            'confirm_password': 'debil',
        })
        assert resp.status_code == 400
