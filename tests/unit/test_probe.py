# tests/unit/test_probe.py
"""Tests unitarios para modules/monitorizacion/probe.py"""
import socket
import pytest
from unittest.mock import MagicMock, patch

from modules.monitorizacion.probe import probe_service, _probe_tcp, _probe_udp


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tcp_socket_mock(connect_ex_result=0, side_effect=None):
    """Crea un mock de socket TCP que simula la respuesta indicada."""
    sock = MagicMock()
    sock.__enter__ = MagicMock(return_value=sock)
    sock.__exit__ = MagicMock(return_value=False)
    if side_effect is not None:
        sock.connect_ex.side_effect = side_effect
    else:
        sock.connect_ex.return_value = connect_ex_result
    return sock


def _udp_socket_mock(recvfrom_result=None, recvfrom_side_effect=None,
                     sendto_side_effect=None):
    """Crea un mock de socket UDP."""
    sock = MagicMock()
    sock.__enter__ = MagicMock(return_value=sock)
    sock.__exit__ = MagicMock(return_value=False)
    if sendto_side_effect is not None:
        sock.sendto.side_effect = sendto_side_effect
    if recvfrom_side_effect is not None:
        sock.recvfrom.side_effect = recvfrom_side_effect
    elif recvfrom_result is not None:
        sock.recvfrom.return_value = recvfrom_result
    return sock


# ── probe_service (enrutamiento TCP / UDP) ────────────────────────────────────

class TestProbeService:
    def test_sin_protocolo_usa_tcp(self):
        with patch('modules.monitorizacion.probe._probe_tcp') as mock_tcp:
            mock_tcp.return_value = {'status': 'up', 'latency_ms': 5.0, 'message': 'ok'}
            probe_service('127.0.0.1', 80)
        mock_tcp.assert_called_once_with('127.0.0.1', 80, 3.0)

    def test_protocolo_tcp_explicito(self):
        with patch('modules.monitorizacion.probe._probe_tcp') as mock_tcp:
            mock_tcp.return_value = {'status': 'up', 'latency_ms': 1.0, 'message': ''}
            probe_service('127.0.0.1', 443, protocol='TCP')
        mock_tcp.assert_called_once()

    def test_protocolo_tcp_minusculas(self):
        with patch('modules.monitorizacion.probe._probe_tcp') as mock_tcp:
            mock_tcp.return_value = {'status': 'up', 'latency_ms': 1.0, 'message': ''}
            probe_service('127.0.0.1', 80, protocol='tcp')
        mock_tcp.assert_called_once()

    def test_protocolo_udp(self):
        with patch('modules.monitorizacion.probe._probe_udp') as mock_udp:
            mock_udp.return_value = {'status': 'warning', 'latency_ms': None, 'message': ''}
            probe_service('127.0.0.1', 53, protocol='UDP')
        mock_udp.assert_called_once()

    def test_protocolo_udp_minusculas(self):
        with patch('modules.monitorizacion.probe._probe_udp') as mock_udp:
            mock_udp.return_value = {'status': 'up', 'latency_ms': 2.0, 'message': ''}
            probe_service('10.0.0.1', 53, protocol='udp')
        mock_udp.assert_called_once()

    def test_timeout_personalizado_se_pasa(self):
        with patch('modules.monitorizacion.probe._probe_tcp') as mock_tcp:
            mock_tcp.return_value = {'status': 'up', 'latency_ms': 5.0, 'message': ''}
            probe_service('127.0.0.1', 80, timeout=10.0)
        mock_tcp.assert_called_once_with('127.0.0.1', 80, 10.0)


# ── _probe_tcp ────────────────────────────────────────────────────────────────

class TestProbeTcp:
    def test_conexion_exitosa_devuelve_up(self):
        sock = _tcp_socket_mock(connect_ex_result=0)
        with patch('modules.monitorizacion.probe.socket.socket', return_value=sock):
            result = _probe_tcp('127.0.0.1', 80, 3.0)
        assert result['status'] == 'up'
        assert result['latency_ms'] is not None
        assert result['latency_ms'] >= 0.0

    def test_mensaje_conexion_exitosa_incluye_ip_y_puerto(self):
        sock = _tcp_socket_mock(connect_ex_result=0)
        with patch('modules.monitorizacion.probe.socket.socket', return_value=sock):
            result = _probe_tcp('192.168.1.1', 8080, 3.0)
        assert '192.168.1.1' in result['message']
        assert '8080' in result['message']

    def test_conexion_rechazada_devuelve_down(self):
        sock = _tcp_socket_mock(connect_ex_result=111)  # ECONNREFUSED
        with patch('modules.monitorizacion.probe.socket.socket', return_value=sock):
            result = _probe_tcp('127.0.0.1', 9999, 3.0)
        assert result['status'] == 'down'
        assert result['latency_ms'] is None

    def test_timeout_devuelve_down(self):
        sock = _tcp_socket_mock(side_effect=socket.timeout)
        with patch('modules.monitorizacion.probe.socket.socket', return_value=sock):
            result = _probe_tcp('10.0.0.1', 80, 1.0)
        assert result['status'] == 'down'
        assert result['latency_ms'] is None
        msg = result['message'].lower()
        assert 'timeout' in msg or 'time' in msg

    def test_dns_error_devuelve_down(self):
        sock = _tcp_socket_mock(side_effect=socket.gaierror('Name not known'))
        with patch('modules.monitorizacion.probe.socket.socket', return_value=sock):
            result = _probe_tcp('noexiste.invalid', 80, 3.0)
        assert result['status'] == 'down'
        assert result['latency_ms'] is None

    def test_oserror_devuelve_down(self):
        sock = _tcp_socket_mock(side_effect=OSError('Network unreachable'))
        with patch('modules.monitorizacion.probe.socket.socket', return_value=sock):
            result = _probe_tcp('10.255.255.255', 80, 3.0)
        assert result['status'] == 'down'

    def test_resultado_tiene_claves_requeridas(self):
        sock = _tcp_socket_mock(connect_ex_result=0)
        with patch('modules.monitorizacion.probe.socket.socket', return_value=sock):
            result = _probe_tcp('127.0.0.1', 80, 3.0)
        assert 'status' in result
        assert 'latency_ms' in result
        assert 'message' in result

    def test_errno_incluido_en_mensaje_cuando_down(self):
        sock = _tcp_socket_mock(connect_ex_result=111)
        with patch('modules.monitorizacion.probe.socket.socket', return_value=sock):
            result = _probe_tcp('127.0.0.1', 9999, 3.0)
        # El mensaje debe mencionar el errno
        assert '111' in result['message']


# ── _probe_udp ────────────────────────────────────────────────────────────────

class TestProbeUdp:
    def test_respuesta_udp_devuelve_up(self):
        sock = _udp_socket_mock(recvfrom_result=(b'\x00', ('127.0.0.1', 53)))
        with patch('modules.monitorizacion.probe.socket.socket', return_value=sock):
            result = _probe_udp('127.0.0.1', 53, 3.0)
        assert result['status'] == 'up'
        assert result['latency_ms'] is not None
        assert result['latency_ms'] >= 0.0

    def test_timeout_udp_es_warning(self):
        """UDP sin respuesta es no concluyente → 'warning'."""
        sock = _udp_socket_mock(recvfrom_side_effect=socket.timeout)
        with patch('modules.monitorizacion.probe.socket.socket', return_value=sock):
            result = _probe_udp('127.0.0.1', 53, 1.0)
        assert result['status'] == 'warning'
        assert result['latency_ms'] is None

    def test_icmp_unreachable_devuelve_down(self):
        """ConnectionResetError (ICMP port unreachable) → 'down'."""
        sock = _udp_socket_mock(recvfrom_side_effect=ConnectionResetError)
        with patch('modules.monitorizacion.probe.socket.socket', return_value=sock):
            result = _probe_udp('127.0.0.1', 9999, 3.0)
        assert result['status'] == 'down'
        assert result['latency_ms'] is None

    def test_dns_error_udp_devuelve_down(self):
        sock = _udp_socket_mock(sendto_side_effect=socket.gaierror('DNS failure'))
        with patch('modules.monitorizacion.probe.socket.socket', return_value=sock):
            result = _probe_udp('noexiste.invalid', 53, 3.0)
        assert result['status'] == 'down'

    def test_oserror_udp_devuelve_down(self):
        sock = _udp_socket_mock(sendto_side_effect=OSError('Network error'))
        with patch('modules.monitorizacion.probe.socket.socket', return_value=sock):
            result = _probe_udp('10.255.255.255', 53, 3.0)
        assert result['status'] == 'down'

    def test_resultado_udp_tiene_claves_requeridas(self):
        sock = _udp_socket_mock(recvfrom_result=(b'\x00', ('127.0.0.1', 53)))
        with patch('modules.monitorizacion.probe.socket.socket', return_value=sock):
            result = _probe_udp('127.0.0.1', 53, 3.0)
        assert 'status' in result
        assert 'latency_ms' in result
        assert 'message' in result

    def test_mensaje_warning_menciona_no_concluyente(self):
        sock = _udp_socket_mock(recvfrom_side_effect=socket.timeout)
        with patch('modules.monitorizacion.probe.socket.socket', return_value=sock):
            result = _probe_udp('127.0.0.1', 53, 1.0)
        assert 'concluyente' in result['message'].lower() or 'sin respuesta' in result['message'].lower()
