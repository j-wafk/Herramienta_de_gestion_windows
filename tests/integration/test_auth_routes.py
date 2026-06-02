# tests/integration/test_auth_routes.py
"""Tests de integración para el módulo de autenticación.

Cubre: login/logout, protección de rutas por rol, perfil, gestión de usuarios.
Usa SQLite en memoria para no requerir PostgreSQL.
"""
import os
import json

os.environ.setdefault('SECRET_KEY', 'test_secret_auth')
os.environ.setdefault('ADMIN_PASSWORD', 'Admin12345678!')
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


# ── Gestión avanzada de usuarios ─────────────────────────────────────────────

class TestUserManagement:
    """Tests adicionales para users CRUD y reglas de roles."""

    def _create_user(self, client, **kwargs):
        defaults = {
            'username': 'tmpusr',
            'password': 'TempPass@1234',
            'role': 'operador',
        }
        defaults.update(kwargs)
        return client.post('/auth/api/usuarios', json=defaults)

    def _cleanup(self, app, username):
        with app.app_context():
            from database import db
            from database.models import User
            u = User.query.filter_by(username=username).first()
            if u:
                db.session.delete(u)
                db.session.commit()

    def test_create_user_invalid_username_returns_400(self, logged_client):
        resp = self._create_user(logged_client, username='!!invalid!!')
        assert resp.status_code == 400

    def test_create_user_with_email(self, app, logged_client):
        resp = self._create_user(logged_client, username='userwithmail',
                                 email='test@example.com')
        assert resp.status_code == 201
        self._cleanup(app, 'userwithmail')

    def test_create_user_invalid_email_returns_400(self, logged_client):
        resp = self._create_user(logged_client, username='bademailusr',
                                 email='not-an-email')
        assert resp.status_code == 400

    def test_create_user_long_fullname_returns_400(self, logged_client):
        resp = self._create_user(logged_client, username='longnameusr',
                                 full_name='x' * 130)
        assert resp.status_code == 400

    def test_create_user_with_fullname(self, app, logged_client):
        resp = self._create_user(logged_client, username='fnameusr',
                                 full_name='Juan Pérez')
        assert resp.status_code == 201
        self._cleanup(app, 'fnameusr')

    def test_update_nonexistent_user_returns_404(self, logged_client):
        resp = logged_client.put('/auth/api/usuarios/99999',
                                 json={'role': 'admin'})
        assert resp.status_code == 404

    def test_update_user_username_conflict_returns_409(self, app, logged_client, admin_username):
        # Crear un usuario
        self._create_user(logged_client, username='conflictusr')
        with app.app_context():
            from database.models import User
            u = User.query.filter_by(username='conflictusr').first()
            uid = u.id if u else None
        if uid:
            # Intentar cambiar a un nombre ya existente (admin)
            resp = logged_client.put(f'/auth/api/usuarios/{uid}',
                                     json={'username': admin_username})
            assert resp.status_code == 409
        self._cleanup(app, 'conflictusr')

    def test_update_user_invalid_username_returns_400(self, app, logged_client):
        self._create_user(logged_client, username='updtmpuser')
        with app.app_context():
            from database.models import User
            u = User.query.filter_by(username='updtmpuser').first()
            uid = u.id if u else None
        if uid:
            resp = logged_client.put(f'/auth/api/usuarios/{uid}',
                                     json={'username': '!!badname!!'})
            assert resp.status_code == 400
        self._cleanup(app, 'updtmpuser')

    def test_update_user_invalid_role_returns_400(self, app, logged_client):
        self._create_user(logged_client, username='updroleuser')
        with app.app_context():
            from database.models import User
            u = User.query.filter_by(username='updroleuser').first()
            uid = u.id if u else None
        if uid:
            resp = logged_client.put(f'/auth/api/usuarios/{uid}',
                                     json={'role': 'bad_role'})
            assert resp.status_code == 400
        self._cleanup(app, 'updroleuser')

    def test_update_user_email(self, app, logged_client):
        self._create_user(logged_client, username='updemailuser')
        with app.app_context():
            from database.models import User
            u = User.query.filter_by(username='updemailuser').first()
            uid = u.id if u else None
        if uid:
            resp = logged_client.put(f'/auth/api/usuarios/{uid}',
                                     json={'email': 'new@example.com'})
            assert resp.status_code == 200
        self._cleanup(app, 'updemailuser')

    def test_update_user_invalid_email_returns_400(self, app, logged_client):
        self._create_user(logged_client, username='updbademailuser')
        with app.app_context():
            from database.models import User
            u = User.query.filter_by(username='updbademailuser').first()
            uid = u.id if u else None
        if uid:
            resp = logged_client.put(f'/auth/api/usuarios/{uid}',
                                     json={'email': 'invalid'})
            assert resp.status_code == 400
        self._cleanup(app, 'updbademailuser')

    def test_update_user_long_fullname_returns_400(self, app, logged_client):
        self._create_user(logged_client, username='updfnameuser')
        with app.app_context():
            from database.models import User
            u = User.query.filter_by(username='updfnameuser').first()
            uid = u.id if u else None
        if uid:
            resp = logged_client.put(f'/auth/api/usuarios/{uid}',
                                     json={'full_name': 'x' * 130})
            assert resp.status_code == 400
        self._cleanup(app, 'updfnameuser')

    def test_update_user_password(self, app, logged_client):
        self._create_user(logged_client, username='updpwduser')
        with app.app_context():
            from database.models import User
            u = User.query.filter_by(username='updpwduser').first()
            uid = u.id if u else None
        if uid:
            resp = logged_client.put(f'/auth/api/usuarios/{uid}',
                                     json={'password': 'NuevoPassw@1234'})
            assert resp.status_code == 200
        self._cleanup(app, 'updpwduser')

    def test_update_user_weak_password_returns_400(self, app, logged_client):
        self._create_user(logged_client, username='updweakpwduser')
        with app.app_context():
            from database.models import User
            u = User.query.filter_by(username='updweakpwduser').first()
            uid = u.id if u else None
        if uid:
            resp = logged_client.put(f'/auth/api/usuarios/{uid}',
                                     json={'password': '123'})
            assert resp.status_code == 400
        self._cleanup(app, 'updweakpwduser')

    def test_update_self_isactive_false_returns_400(self, logged_client, admin_user_id):
        resp = logged_client.put(f'/auth/api/usuarios/{admin_user_id}',
                                 json={'is_active': False})
        assert resp.status_code == 400

    def test_delete_self_returns_400(self, logged_client, admin_user_id):
        resp = logged_client.delete(f'/auth/api/usuarios/{admin_user_id}')
        assert resp.status_code == 400

    def test_delete_nonexistent_returns_404(self, logged_client):
        resp = logged_client.delete('/auth/api/usuarios/99999')
        assert resp.status_code == 404

    def test_delete_user_success(self, app, logged_client):
        self._create_user(logged_client, username='deletemeuser')
        with app.app_context():
            from database.models import User
            u = User.query.filter_by(username='deletemeuser').first()
            uid = u.id if u else None
        if uid:
            resp = logged_client.delete(f'/auth/api/usuarios/{uid}')
            assert resp.status_code == 200

    def test_unlock_nonexistent_returns_404(self, logged_client):
        resp = logged_client.post('/auth/api/usuarios/99999/unlock')
        assert resp.status_code == 404

    def test_unlock_user_success(self, app, logged_client):
        self._create_user(logged_client, username='unlockuser')
        with app.app_context():
            from database.models import User
            from datetime import datetime, timedelta
            from database import db
            u = User.query.filter_by(username='unlockuser').first()
            if u:
                u.locked_until = datetime.utcnow() + timedelta(minutes=30)
                u.failed_attempts = 10
                db.session.commit()
                uid = u.id
            else:
                uid = None
        if uid:
            resp = logged_client.post(f'/auth/api/usuarios/{uid}/unlock')
            assert resp.status_code == 200
        self._cleanup(app, 'unlockuser')


# ── Audit / Registros ─────────────────────────────────────────────────────────

class TestAuditExport:
    def test_registros_invalid_format_returns_400(self, logged_client):
        resp = logged_client.get('/auth/api/registros/export?format=invalid')
        assert resp.status_code == 400

    def test_registros_csv_export(self, logged_client):
        resp = logged_client.get('/auth/api/registros/export?format=csv')
        assert resp.status_code == 200
        assert 'text/csv' in resp.content_type

    def test_registros_xlsx_export(self, logged_client):
        resp = logged_client.get('/auth/api/registros/export?format=xlsx')
        assert resp.status_code == 200

    def test_registros_pdf_export(self, logged_client):
        resp = logged_client.get('/auth/api/registros/export?format=pdf')
        assert resp.status_code == 200
        assert 'application/pdf' in resp.content_type

    def test_registros_pagination(self, logged_client):
        resp = logged_client.get('/auth/api/registros?page=1&per_page=10')
        assert resp.status_code == 200

    def test_registros_invalid_pagination_uses_defaults(self, logged_client):
        resp = logged_client.get('/auth/api/registros?page=abc&per_page=xyz')
        assert resp.status_code == 200

    def test_registros_filters(self, logged_client):
        resp = logged_client.get(
            '/auth/api/registros?user=admin&action=login_success&q=login'
        )
        assert resp.status_code == 200

    def test_registros_date_filter(self, logged_client):
        resp = logged_client.get('/auth/api/registros?from=2026-01-01&to=2026-12-31')
        assert resp.status_code == 200


# ── Profile extendido ─────────────────────────────────────────────────────────

class TestProfileExtended:
    def test_update_email_valid(self, logged_client):
        resp = logged_client.post('/auth/api/profile/update', json={
            'email': 'admin@example.com',
        })
        assert resp.status_code == 200

    def test_update_email_invalid_returns_400(self, logged_client):
        resp = logged_client.post('/auth/api/profile/update', json={
            'email': 'invalid email',
        })
        assert resp.status_code == 400

    def test_update_fullname(self, logged_client):
        resp = logged_client.post('/auth/api/profile/update', json={
            'full_name': 'Test User',
        })
        assert resp.status_code == 200

    def test_update_fullname_too_long_returns_400(self, logged_client):
        resp = logged_client.post('/auth/api/profile/update', json={
            'full_name': 'x' * 130,
        })
        assert resp.status_code == 400

    def test_update_tema_invalido_returns_400(self, logged_client):
        resp = logged_client.post('/auth/api/profile/update', json={
            'theme': 'rainbow',
        })
        assert resp.status_code == 400

    def test_update_email_notifications(self, logged_client):
        resp = logged_client.post('/auth/api/profile/update', json={
            'email_notifications': True,
        })
        assert resp.status_code == 200


# ── Notificaciones (preferences) ──────────────────────────────────────────────

class TestNotificationPrefs:
    def test_get_returns_dict_with_defaults(self, logged_client):
        resp = logged_client.get('/auth/api/profile/notifications')
        assert resp.status_code == 200
        data = resp.get_json()
        for key in ('machine_offline', 'service_down', 'backup_failed',
                    'backup_completed', 'daily_summary'):
            assert key in data

    def test_update_one_field(self, logged_client):
        resp = logged_client.post('/auth/api/profile/notifications', json={
            'machine_offline': False,
        })
        assert resp.status_code == 200
        # Restaurar
        logged_client.post('/auth/api/profile/notifications', json={
            'machine_offline': True,
        })

    def test_update_multiple_fields(self, logged_client):
        resp = logged_client.post('/auth/api/profile/notifications', json={
            'service_down': True,
            'backup_failed': True,
            'daily_summary': True,
        })
        assert resp.status_code == 200

    def test_update_no_changes_returns_200(self, logged_client):
        # Una vez aplicado un valor, repetirlo no cambia nada
        logged_client.post('/auth/api/profile/notifications', json={
            'machine_offline': True,
        })
        resp = logged_client.post('/auth/api/profile/notifications', json={
            'machine_offline': True,
        })
        assert resp.status_code == 200


# ── Password change success ───────────────────────────────────────────────────

class TestPasswordChangeFlow:
    def test_change_password_success(self, app, logged_client, admin_user_id):
        """Cambiar contraseña con valores válidos."""
        old_pwd = os.environ['ADMIN_PASSWORD']
        new_pwd = 'NuevaContrasena@2026'

        resp = logged_client.post('/auth/api/profile/password', json={
            'current_password': old_pwd,
            'new_password': new_pwd,
            'confirm_password': new_pwd,
        })
        assert resp.status_code == 200

        # Restaurar contraseña
        logged_client.post('/auth/api/profile/password', json={
            'current_password': new_pwd,
            'new_password': old_pwd,
            'confirm_password': old_pwd,
        })


# ── Decorator require_role - rutas no-/api/ ──────────────────────────────────

class TestRequireRoleRedirect:
    """Test que rutas no-API redirigen a login cuando no estás autenticado."""

    def test_unauthenticated_page_redirects(self, client):
        resp = client.get('/auth/usuarios', follow_redirects=False)
        assert resp.status_code == 302
