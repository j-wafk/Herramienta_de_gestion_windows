"""Tests unitarios para modules/notifications/dispatch.py."""
import os
from unittest.mock import patch, MagicMock
from datetime import datetime
import pytest

os.environ.setdefault('SECRET_KEY', 'test_secret')
os.environ.setdefault('ADMIN_PASSWORD', 'Admin12345678!')
os.environ.setdefault('FIELD_ENCRYPTION_KEY', 'test_field_encryption_key_32bytes!!')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')


@pytest.fixture(scope='module')
def app():
    from main import create_app
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def fake_user():
    """Crea un User mock con email."""
    u = MagicMock()
    u.id = 1
    u.email = 'user@example.com'
    u.username = 'testuser'
    u.is_active = True
    return u


@pytest.fixture
def fake_machine():
    m = MagicMock()
    m.id = 5
    m.name = 'TestMachine'
    m.last_seen = datetime(2026, 5, 1, 12, 0, 0)
    return m


@pytest.fixture
def fake_service():
    s = MagicMock()
    s.id = 7
    s.name = 'WebSvc'
    s.last_message = 'Connection refused'
    return s


@pytest.fixture
def fake_run():
    r = MagicMock()
    r.id = 11
    r.started_at = datetime(2026, 5, 1, 10, 0, 0)
    r.finished_at = datetime(2026, 5, 1, 10, 5, 0)
    r.error = 'disk full'
    r.backup_type_snapshot = 'full'
    return r


# ─── _recipients_for ───────────────────────────────────────────────────────────

class TestRecipientsFor:
    @patch('modules.notifications.dispatch.NotificationPreference')
    @patch('modules.notifications.dispatch.User')
    def test_no_users_returns_empty(self, mock_user_cls, mock_pref_cls, app):
        with app.app_context():
            mock_user_cls.query.filter.return_value.all.return_value = []
            from modules.notifications.dispatch import _recipients_for
            result = _recipients_for('machine_offline')
            assert result == []

    @patch('modules.notifications.dispatch.NotificationPreference')
    @patch('modules.notifications.dispatch.User')
    def test_default_applies_when_no_pref(self, mock_user_cls, mock_pref_cls, app, fake_user):
        with app.app_context():
            mock_user_cls.query.filter.return_value.all.return_value = [fake_user]
            mock_pref_cls.query.all.return_value = []
            from modules.notifications.dispatch import _recipients_for
            # machine_offline default=True → debe incluir al user
            result = _recipients_for('machine_offline')
            assert fake_user.email in result

    @patch('modules.notifications.dispatch.NotificationPreference')
    @patch('modules.notifications.dispatch.User')
    def test_user_pref_disabled_excludes(self, mock_user_cls, mock_pref_cls, app, fake_user):
        with app.app_context():
            mock_user_cls.query.filter.return_value.all.return_value = [fake_user]
            pref = MagicMock()
            pref.user_id = fake_user.id
            pref.machine_offline = False
            mock_pref_cls.query.all.return_value = [pref]
            from modules.notifications.dispatch import _recipients_for
            result = _recipients_for('machine_offline')
            assert fake_user.email not in result

    @patch('modules.notifications.dispatch.NotificationPreference')
    @patch('modules.notifications.dispatch.User')
    def test_user_pref_enabled_includes(self, mock_user_cls, mock_pref_cls, app, fake_user):
        with app.app_context():
            mock_user_cls.query.filter.return_value.all.return_value = [fake_user]
            pref = MagicMock()
            pref.user_id = fake_user.id
            pref.service_down = True
            mock_pref_cls.query.all.return_value = [pref]
            from modules.notifications.dispatch import _recipients_for
            result = _recipients_for('service_down')
            assert fake_user.email in result

    @patch('modules.notifications.dispatch.NotificationPreference')
    @patch('modules.notifications.dispatch.User')
    def test_daily_summary_default_false(self, mock_user_cls, mock_pref_cls, app, fake_user):
        with app.app_context():
            mock_user_cls.query.filter.return_value.all.return_value = [fake_user]
            mock_pref_cls.query.all.return_value = []
            from modules.notifications.dispatch import _recipients_for
            # daily_summary default=False
            result = _recipients_for('daily_summary')
            assert result == []


# ─── notify_machine_offline ───────────────────────────────────────────────────

class TestNotifyMachineOffline:
    @patch('modules.notifications.dispatch._recipients_for', return_value=[])
    def test_no_recipients_returns_zero(self, mock_rec, app, fake_machine):
        with app.app_context():
            from modules.notifications.dispatch import notify_machine_offline
            assert notify_machine_offline(fake_machine) == 0

    @patch('modules.notifications.dispatch.send_email_async', return_value=1)
    @patch('modules.notifications.dispatch.render_template',
           return_value='<html>offline</html>')
    @patch('modules.notifications.dispatch._recipients_for',
           return_value=['user@example.com'])
    def test_queues_email_per_recipient(self, mock_rec, mock_render, mock_send,
                                        app, fake_machine):
        with app.app_context():
            from modules.notifications.dispatch import notify_machine_offline
            result = notify_machine_offline(fake_machine)
            assert result == 1
            mock_send.assert_called_once()

    @patch('modules.notifications.dispatch.render_template',
           side_effect=RuntimeError('render error'))
    @patch('modules.notifications.dispatch._recipients_for',
           return_value=['user@example.com'])
    def test_render_exception_returns_zero(self, mock_rec, mock_render,
                                           app, fake_machine):
        with app.app_context():
            from modules.notifications.dispatch import notify_machine_offline
            assert notify_machine_offline(fake_machine) == 0

    @patch('modules.notifications.dispatch.send_email_async', return_value=1)
    @patch('modules.notifications.dispatch.render_template', return_value='<html>x</html>')
    @patch('modules.notifications.dispatch._recipients_for',
           return_value=['user@example.com'])
    def test_no_last_seen_uses_none(self, mock_rec, mock_render, mock_send, app):
        machine = MagicMock()
        machine.id = 1
        machine.name = 'X'
        machine.last_seen = None
        with app.app_context():
            from modules.notifications.dispatch import notify_machine_offline
            result = notify_machine_offline(machine)
            assert result == 1


# ─── notify_service_down ──────────────────────────────────────────────────────

class TestNotifyServiceDown:
    @patch('modules.notifications.dispatch._recipients_for', return_value=[])
    def test_no_recipients_returns_zero(self, mock_rec, app, fake_service):
        with app.app_context():
            from modules.notifications.dispatch import notify_service_down
            assert notify_service_down(fake_service, 'up') == 0

    @patch('modules.notifications.dispatch.send_email_async', return_value=1)
    @patch('modules.notifications.dispatch.render_template', return_value='<html>down</html>')
    @patch('modules.notifications.dispatch._recipients_for',
           return_value=['a@example.com', 'b@example.com'])
    def test_queues_multiple(self, mock_rec, mock_render, mock_send,
                             app, fake_service):
        with app.app_context():
            from modules.notifications.dispatch import notify_service_down
            result = notify_service_down(fake_service, 'up', machine_name='M1')
            assert result == 2

    @patch('modules.notifications.dispatch.render_template',
           side_effect=Exception('boom'))
    @patch('modules.notifications.dispatch._recipients_for',
           return_value=['x@y.com'])
    def test_render_exception(self, mock_rec, mock_render, app, fake_service):
        with app.app_context():
            from modules.notifications.dispatch import notify_service_down
            assert notify_service_down(fake_service, 'up') == 0


# ─── notify_backup_failed ─────────────────────────────────────────────────────

class TestNotifyBackupFailed:
    @patch('modules.notifications.dispatch._recipients_for', return_value=[])
    def test_no_recipients(self, mock_rec, app, fake_run):
        with app.app_context():
            from modules.notifications.dispatch import notify_backup_failed
            assert notify_backup_failed(fake_run, 'JobA') == 0

    @patch('modules.notifications.dispatch.send_email_async', return_value=1)
    @patch('modules.notifications.dispatch.render_template', return_value='<html>fail</html>')
    @patch('modules.notifications.dispatch._recipients_for',
           return_value=['admin@x.com'])
    def test_sends_email(self, mock_rec, mock_render, mock_send, app, fake_run):
        with app.app_context():
            from modules.notifications.dispatch import notify_backup_failed
            result = notify_backup_failed(fake_run, 'JobA', machine_name='M1')
            assert result == 1

    @patch('modules.notifications.dispatch.render_template',
           side_effect=Exception('fail'))
    @patch('modules.notifications.dispatch._recipients_for',
           return_value=['x@x.com'])
    def test_render_exception(self, mock_rec, mock_render, app, fake_run):
        with app.app_context():
            from modules.notifications.dispatch import notify_backup_failed
            assert notify_backup_failed(fake_run, 'JobA') == 0


# ─── notify_backup_completed ──────────────────────────────────────────────────

class TestNotifyBackupCompleted:
    @patch('modules.notifications.dispatch._recipients_for', return_value=[])
    def test_no_recipients(self, mock_rec, app, fake_run):
        with app.app_context():
            from modules.notifications.dispatch import notify_backup_completed
            assert notify_backup_completed(fake_run, 'JobA') == 0

    @patch('modules.notifications.dispatch.send_email_async', return_value=1)
    @patch('modules.notifications.dispatch.render_template', return_value='<html>ok</html>')
    @patch('modules.notifications.dispatch._recipients_for',
           return_value=['admin@x.com'])
    def test_with_optional_params(self, mock_rec, mock_render, mock_send,
                                  app, fake_run):
        with app.app_context():
            from modules.notifications.dispatch import notify_backup_completed
            result = notify_backup_completed(fake_run, 'JobA',
                                              machine_name='M1',
                                              size_str='1.5 GB',
                                              files=42,
                                              duration_str='30 s')
            assert result == 1

    @patch('modules.notifications.dispatch.render_template',
           side_effect=Exception('boom'))
    @patch('modules.notifications.dispatch._recipients_for',
           return_value=['x@y.com'])
    def test_render_exception(self, mock_rec, mock_render, app, fake_run):
        with app.app_context():
            from modules.notifications.dispatch import notify_backup_completed
            assert notify_backup_completed(fake_run, 'JobA') == 0


# ─── notify_welcome ───────────────────────────────────────────────────────────

class TestNotifyWelcome:
    def test_no_email_returns_zero(self, app):
        user = MagicMock()
        user.email = None
        with app.app_context():
            from modules.notifications.dispatch import notify_welcome
            assert notify_welcome(user) == 0

    @patch('modules.notifications.dispatch.send_email_async', return_value=99)
    @patch('modules.notifications.dispatch.render_template',
           return_value='<html>welcome</html>')
    def test_sends_email(self, mock_render, mock_send, app, fake_user):
        with app.app_context():
            from modules.notifications.dispatch import notify_welcome
            result = notify_welcome(fake_user)
            assert result == 99

    @patch('modules.notifications.dispatch.render_template',
           side_effect=RuntimeError('boom'))
    def test_render_exception(self, mock_render, app, fake_user):
        with app.app_context():
            from modules.notifications.dispatch import notify_welcome
            assert notify_welcome(fake_user) == 0


# ─── notify_password_changed ──────────────────────────────────────────────────

class TestNotifyPasswordChanged:
    def test_no_email_returns_zero(self, app):
        user = MagicMock()
        user.email = None
        with app.app_context():
            from modules.notifications.dispatch import notify_password_changed
            assert notify_password_changed(user) == 0

    @patch('modules.notifications.dispatch.send_email_async', return_value=42)
    @patch('modules.notifications.dispatch.render_template',
           return_value='<html>changed</html>')
    def test_sends_email_with_ip(self, mock_render, mock_send, app, fake_user):
        with app.app_context():
            from modules.notifications.dispatch import notify_password_changed
            result = notify_password_changed(fake_user, ip='10.0.0.1')
            assert result == 42

    @patch('modules.notifications.dispatch.render_template',
           side_effect=Exception('fail'))
    def test_render_exception(self, mock_render, app, fake_user):
        with app.app_context():
            from modules.notifications.dispatch import notify_password_changed
            assert notify_password_changed(fake_user) == 0
