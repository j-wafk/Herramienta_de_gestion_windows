# tests/unit/test_mailer.py
"""Tests unitarios para utils/mailer.py"""
import smtplib
import pytest
from unittest.mock import MagicMock, patch


# ── is_valid_email ────────────────────────────────────────────────────────────

class TestIsValidEmail:
    def test_email_simple_valido(self):
        from utils.mailer import is_valid_email
        assert is_valid_email('user@example.com') is True

    def test_email_con_subdominio(self):
        from utils.mailer import is_valid_email
        assert is_valid_email('user@mail.example.co.uk') is True

    def test_email_con_mas(self):
        from utils.mailer import is_valid_email
        assert is_valid_email('user+tag@example.com') is True

    def test_email_con_puntos_en_local(self):
        from utils.mailer import is_valid_email
        assert is_valid_email('first.last@domain.org') is True

    def test_email_con_guion_en_dominio(self):
        from utils.mailer import is_valid_email
        assert is_valid_email('user@my-domain.com') is True

    def test_sin_arroba(self):
        from utils.mailer import is_valid_email
        assert is_valid_email('userexample.com') is False

    def test_sin_dominio(self):
        from utils.mailer import is_valid_email
        assert is_valid_email('user@') is False

    def test_sin_tld(self):
        from utils.mailer import is_valid_email
        assert is_valid_email('user@example') is False

    def test_tld_un_caracter(self):
        from utils.mailer import is_valid_email
        assert is_valid_email('user@example.c') is False

    def test_vacio(self):
        from utils.mailer import is_valid_email
        assert is_valid_email('') is False

    def test_none(self):
        from utils.mailer import is_valid_email
        assert is_valid_email(None) is False

    def test_con_espacios(self):
        from utils.mailer import is_valid_email
        assert is_valid_email('user @example.com') is False

    def test_solo_arroba(self):
        from utils.mailer import is_valid_email
        assert is_valid_email('@') is False


# ── _html_to_text ─────────────────────────────────────────────────────────────

class TestHtmlToText:
    def test_quita_etiquetas(self):
        from utils.mailer import _html_to_text
        assert _html_to_text('<p>Hola <b>mundo</b></p>') == 'Hola mundo'

    def test_texto_sin_etiquetas(self):
        from utils.mailer import _html_to_text
        assert _html_to_text('texto plano') == 'texto plano'

    def test_vacio(self):
        from utils.mailer import _html_to_text
        assert _html_to_text('') == ''

    def test_none(self):
        from utils.mailer import _html_to_text
        assert _html_to_text(None) == ''

    def test_solo_etiquetas(self):
        from utils.mailer import _html_to_text
        assert _html_to_text('<br/><hr/>') == ''

    def test_conserva_contenido_entre_etiquetas(self):
        from utils.mailer import _html_to_text
        result = _html_to_text('<h1>Título</h1><p>Cuerpo del mensaje.</p>')
        assert 'Título' in result
        assert 'Cuerpo del mensaje.' in result


# ── send_email ────────────────────────────────────────────────────────────────

class TestSendEmail:
    def _make_config(self, enabled=True):
        """Devuelve un mock de Config con valores por defecto razonables."""
        cfg = MagicMock()
        cfg.MAIL_ENABLED = enabled
        cfg.MAIL_FROM = 'noreply@test.com'
        cfg.MAIL_FROM_NAME = 'TestApp'
        cfg.SMTP_HOST = 'smtp.test.com'
        cfg.SMTP_PORT = 587
        cfg.SMTP_USE_SSL = False
        cfg.SMTP_USE_TLS = False
        cfg.SMTP_USER = ''
        cfg.SMTP_PASSWORD = ''
        cfg.SMTP_TIMEOUT = 5
        return cfg

    def test_mail_disabled_devuelve_true_sin_enviar(self):
        from utils.mailer import send_email
        with patch('utils.mailer.Config', self._make_config(enabled=False)):
            with patch('smtplib.SMTP') as mock_cls:
                result = send_email('to@example.com', 'Asunto', '<p>Hola</p>')
        assert result is True
        mock_cls.assert_not_called()

    def test_destinatario_invalido_devuelve_false(self):
        from utils.mailer import send_email
        with patch('utils.mailer.Config', self._make_config()):
            result = send_email('no-es-un-email', 'Asunto', '<p>Hola</p>')
        assert result is False

    def test_lista_vacia_devuelve_false(self):
        from utils.mailer import send_email
        with patch('utils.mailer.Config', self._make_config()):
            result = send_email([], 'Asunto', '<p>Hola</p>')
        assert result is False

    def test_to_tipo_invalido_lanza_mailer_error(self):
        from utils.mailer import send_email, MailerError
        with patch('utils.mailer.Config', self._make_config()):
            with pytest.raises(MailerError):
                send_email(12345, 'Asunto', '<p>Hola</p>')

    def test_smtp_exitoso_devuelve_true(self):
        from utils.mailer import send_email
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)
        mock_smtp.sendmail.return_value = {}

        with patch('utils.mailer.Config', self._make_config()):
            with patch('smtplib.SMTP', return_value=mock_smtp):
                result = send_email('valid@example.com', 'Asunto', '<p>Test</p>')

        assert result is True

    def test_smtp_excepcion_devuelve_false(self):
        from utils.mailer import send_email
        with patch('utils.mailer.Config', self._make_config()):
            with patch('smtplib.SMTP',
                       side_effect=smtplib.SMTPConnectError(421, 'Connection refused')):
                result = send_email('valid@example.com', 'Asunto', '<p>Test</p>')
        assert result is False

    def test_socket_timeout_devuelve_false(self):
        import socket
        from utils.mailer import send_email
        with patch('utils.mailer.Config', self._make_config()):
            with patch('smtplib.SMTP', side_effect=socket.timeout):
                result = send_email('valid@example.com', 'Asunto', '<p>Hola</p>')
        assert result is False

    def test_lista_de_destinatarios_validos(self):
        from utils.mailer import send_email
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)
        mock_smtp.sendmail.return_value = {}

        with patch('utils.mailer.Config', self._make_config()):
            with patch('smtplib.SMTP', return_value=mock_smtp):
                result = send_email(
                    ['a@example.com', 'b@example.com'],
                    'Asunto', '<p>Test</p>'
                )
        assert result is True

    def test_lista_con_invalidos_y_validos(self):
        """Si hay al menos un destinatario válido, se intenta el envío."""
        from utils.mailer import send_email
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)
        mock_smtp.sendmail.return_value = {}

        with patch('utils.mailer.Config', self._make_config()):
            with patch('smtplib.SMTP', return_value=mock_smtp):
                result = send_email(
                    ['invalido', 'valid@example.com'],
                    'Asunto', '<p>Hola</p>'
                )
        assert result is True

    def test_asunto_vacio_usa_sin_asunto(self):
        """Asunto vacío se reemplaza por '(sin asunto)'."""
        from utils.mailer import send_email
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)
        mock_smtp.sendmail.return_value = {}

        with patch('utils.mailer.Config', self._make_config()):
            with patch('smtplib.SMTP', return_value=mock_smtp):
                result = send_email('valid@example.com', '', '<p>Hola</p>')
        # Debe llegar a sendmail sin lanzar excepción
        assert result is True

    def test_html_vacio_usa_mensaje_vacio(self):
        from utils.mailer import send_email
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)
        mock_smtp.sendmail.return_value = {}

        with patch('utils.mailer.Config', self._make_config()):
            with patch('smtplib.SMTP', return_value=mock_smtp):
                result = send_email('valid@example.com', 'Asunto', '')
        assert result is True

    def test_ssl_usa_smtp_ssl(self):
        from utils.mailer import send_email
        cfg = self._make_config()
        cfg.SMTP_USE_SSL = True

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)
        mock_smtp.sendmail.return_value = {}

        with patch('utils.mailer.Config', cfg):
            with patch('smtplib.SMTP_SSL', return_value=mock_smtp) as mock_ssl:
                with patch('smtplib.SMTP') as mock_plain:
                    result = send_email('valid@example.com', 'Asunto', '<p>Test</p>')

        assert result is True
        mock_ssl.assert_called_once()
        mock_plain.assert_not_called()
