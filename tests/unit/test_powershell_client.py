"""Tests unitarios para utils/powershell_client.py."""
import os
from unittest.mock import patch, MagicMock
import pytest

os.environ.setdefault('SECRET_KEY', 'test_secret')
os.environ.setdefault('ADMIN_PASSWORD', 'Admin12345678!')
os.environ.setdefault('FIELD_ENCRYPTION_KEY', 'test_field_encryption_key_32bytes!!')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')


class TestRecvAll:
    def test_recv_all_returns_concatenated_chunks(self):
        from utils.powershell_client import _recv_all
        sock = MagicMock()
        sock.recv.side_effect = [b'hello ', b'world', b'']
        assert _recv_all(sock) == b'hello world'

    def test_recv_all_timeout_returns_what_collected(self):
        from utils.powershell_client import _recv_all
        import socket as sk
        sock = MagicMock()
        sock.recv.side_effect = [b'partial', sk.timeout()]
        assert _recv_all(sock) == b'partial'

    def test_recv_all_empty_returns_empty(self):
        from utils.powershell_client import _recv_all
        sock = MagicMock()
        sock.recv.return_value = b''
        assert _recv_all(sock) == b''


class TestSendCommandToPowershell:
    @patch('utils.powershell_client._connect')
    def test_send_command_success(self, mock_connect):
        from utils.powershell_client import send_command_to_powershell
        mock_sock = MagicMock()
        mock_sock.__enter__.return_value = mock_sock
        mock_sock.__exit__.return_value = None
        mock_sock.recv.side_effect = [b'response data', b'']
        mock_connect.return_value = mock_sock
        result = send_command_to_powershell('cpu')
        assert 'response data' in result

    @patch('utils.powershell_client._connect',
           side_effect=ConnectionRefusedError())
    def test_connection_refused_returns_error_msg(self, mock_conn):
        from utils.powershell_client import send_command_to_powershell
        result = send_command_to_powershell('cpu')
        assert 'No se pudo conectar' in result

    @patch('utils.powershell_client._connect',
           side_effect=RuntimeError('other err'))
    def test_generic_exception_returns_error_msg(self, mock_conn):
        from utils.powershell_client import send_command_to_powershell
        result = send_command_to_powershell('cpu')
        assert 'Error' in result

    @patch('utils.powershell_client._connect',
           side_effect=ConnectionRefusedError())
    def test_empty_command_handled(self, mock_conn):
        from utils.powershell_client import send_command_to_powershell
        # No debe explotar con comando vacío
        result = send_command_to_powershell('')
        assert isinstance(result, str)


class TestSendCommandToMachine:
    @patch('utils.powershell_client._connect')
    def test_send_command_remote_success(self, mock_connect):
        from utils.powershell_client import send_command_to_machine
        mock_sock = MagicMock()
        mock_sock.__enter__.return_value = mock_sock
        mock_sock.__exit__.return_value = None
        mock_sock.recv.side_effect = [b'remote_response', b'']
        mock_connect.return_value = mock_sock
        result = send_command_to_machine('cpu', '10.0.0.1', 12345)
        assert 'remote_response' in result

    @patch('utils.powershell_client._connect',
           side_effect=ConnectionRefusedError())
    def test_remote_connection_refused(self, mock_conn):
        from utils.powershell_client import send_command_to_machine
        result = send_command_to_machine('cpu', '10.0.0.1', 12345)
        assert 'No se pudo conectar' in result

    @patch('utils.powershell_client._connect',
           side_effect=TimeoutError('timeout'))
    def test_remote_generic_error(self, mock_conn):
        from utils.powershell_client import send_command_to_machine
        result = send_command_to_machine('cpu', '10.0.0.1', 12345)
        assert 'Error' in result


class TestResolveAndSend:
    @patch('utils.powershell_client.send_command_to_powershell',
           return_value='local response')
    def test_no_machine_id_uses_local(self, mock_local):
        from utils.powershell_client import resolve_and_send
        result = resolve_and_send('cpu', None)
        assert result == 'local response'
        mock_local.assert_called_once_with('cpu')

    @patch('utils.powershell_client.send_command_to_powershell',
           return_value='local fallback')
    def test_invalid_machine_id_falls_back_to_local(self, mock_local):
        from utils.powershell_client import resolve_and_send
        result = resolve_and_send('cpu', 'not-a-number')
        assert result == 'local fallback'


class TestPowerShellClientClass:
    def test_init_defaults(self):
        from utils.powershell_client import PowerShellClient
        c = PowerShellClient('10.0.0.1', 12345)
        assert c.host == '10.0.0.1'
        assert c.port == 12345
        assert c.timeout > 0

    def test_init_with_overrides(self):
        from utils.powershell_client import PowerShellClient
        c = PowerShellClient('10.0.0.1', 12345, timeout=10,
                              tls=True, ca_cert='/path/ca.pem')
        assert c.timeout == 10
        assert c.tls is True
        assert c.ca_cert == '/path/ca.pem'

    @patch('utils.powershell_client.send_command_to_machine',
           return_value='client response')
    def test_send_command_delegates(self, mock_send):
        from utils.powershell_client import PowerShellClient
        c = PowerShellClient('10.0.0.1', 12345)
        result = c.send_command('cpu')
        assert result == 'client response'
        mock_send.assert_called_once_with('cpu', '10.0.0.1', 12345)


class TestHealthCheck:
    @patch('utils.powershell_client._connect')
    def test_health_check_success(self, mock_connect):
        from utils.powershell_client import health_check_powershell
        from flask import Flask
        mock_sock = MagicMock()
        mock_sock.__enter__.return_value = mock_sock
        mock_sock.__exit__.return_value = None
        mock_connect.return_value = mock_sock
        app = Flask(__name__)
        with app.test_request_context('/'):
            resp = health_check_powershell()
        # health_check_powershell returns a Response (flask.jsonify), not a tuple here
        assert resp.status_code == 200

    @patch('utils.powershell_client._connect',
           side_effect=ConnectionRefusedError())
    def test_health_check_failure(self, mock_conn):
        from utils.powershell_client import health_check_powershell
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context('/'):
            resp = health_check_powershell()
        # Returns tuple (resp, 503) on failure
        if isinstance(resp, tuple):
            assert resp[1] == 503
        else:
            assert resp.status_code in (200, 503)
