"""Sondeo TCP/UDP/HTTPS de servicios monitorizados.

Devuelve un dict con:
    status:      'up' | 'down' | 'warning' | 'unknown'
    latency_ms:  float | None
    message:     str con detalle del resultado
"""
import http.client
import socket
import ssl
import time


def probe_service(ip: str, port: int, protocol: str = 'TCP', timeout: float = 3.0) -> dict:
    proto = (protocol or 'TCP').upper()
    if proto == 'UDP':
        return _probe_udp(ip, port, timeout)
    if proto == 'HTTPS':
        return _probe_https(ip, port, timeout)
    return _probe_tcp(ip, port, timeout)


def _probe_tcp(ip: str, port: int, timeout: float) -> dict:
    start = time.monotonic()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            rc = s.connect_ex((ip, int(port)))
        elapsed = (time.monotonic() - start) * 1000.0
        if rc == 0:
            return {
                'status': 'up',
                'latency_ms': round(elapsed, 1),
                'message': f'TCP {ip}:{port} respondió en {elapsed:.0f} ms.',
            }
        return {
            'status': 'down',
            'latency_ms': None,
            'message': f'TCP {ip}:{port} sin respuesta (errno={rc}).',
        }
    except socket.gaierror as e:
        return {'status': 'down', 'latency_ms': None,
                'message': f'No se pudo resolver {ip}: {e}.'}
    except socket.timeout:
        return {'status': 'down', 'latency_ms': None,
                'message': f'Timeout TCP {ip}:{port} tras {timeout:.1f} s.'}
    except OSError as e:
        return {'status': 'down', 'latency_ms': None,
                'message': f'Error TCP {ip}:{port}: {e}.'}


def _probe_https(ip: str, port: int, timeout: float) -> dict:
    """Sondeo HTTPS: HEAD / con certificado no verificado (servicios internos)."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    start = time.monotonic()
    conn = http.client.HTTPSConnection(ip, port, timeout=timeout, context=ctx)
    try:
        conn.request('HEAD', '/')
        resp = conn.getresponse()
        elapsed = (time.monotonic() - start) * 1000.0
        return {
            'status': 'up',
            'latency_ms': round(elapsed, 1),
            'message': f'HTTPS {ip}:{port} respondió HTTP {resp.status} en {elapsed:.0f} ms.',
        }
    except (ConnectionRefusedError, TimeoutError):
        return {'status': 'down', 'latency_ms': None,
                'message': f'HTTPS {ip}:{port}: conexión rechazada o timeout.'}
    except socket.timeout:
        return {'status': 'down', 'latency_ms': None,
                'message': f'HTTPS {ip}:{port}: timeout tras {timeout:.1f} s.'}
    except ssl.SSLError as e:
        elapsed = (time.monotonic() - start) * 1000.0
        return {'status': 'warning', 'latency_ms': round(elapsed, 1),
                'message': f'HTTPS {ip}:{port}: error TLS — {e.reason}.'}
    except socket.gaierror as e:
        return {'status': 'down', 'latency_ms': None,
                'message': f'No se pudo resolver {ip}: {e}.'}
    except OSError as e:
        return {'status': 'down', 'latency_ms': None,
                'message': f'Error HTTPS {ip}:{port}: {e}.'}
    finally:
        conn.close()


def _probe_udp(ip: str, port: int, timeout: float) -> dict:
    """UDP no es orientado a conexión: enviamos un paquete vacío y vemos si
    Windows responde con ICMP "puerto inalcanzable".

    - Recibir respuesta UDP → 'up'
    - ICMP unreachable      → 'down' (puerto cerrado)
    - Timeout sin error     → 'warning' (no concluyente)
    """
    start = time.monotonic()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(timeout)
            s.sendto(b'\x00', (ip, int(port)))
            try:
                s.recvfrom(1024)
                elapsed = (time.monotonic() - start) * 1000.0
                return {'status': 'up', 'latency_ms': round(elapsed, 1),
                        'message': f'UDP {ip}:{port} respondió en {elapsed:.0f} ms.'}
            except socket.timeout:
                return {'status': 'warning', 'latency_ms': None,
                        'message': f'UDP {ip}:{port}: sin respuesta (no concluyente).'}
    except ConnectionResetError:
        return {'status': 'down', 'latency_ms': None,
                'message': f'UDP {ip}:{port}: puerto cerrado (ICMP unreachable).'}
    except socket.gaierror as e:
        return {'status': 'down', 'latency_ms': None,
                'message': f'No se pudo resolver {ip}: {e}.'}
    except OSError as e:
        return {'status': 'down', 'latency_ms': None,
                'message': f'Error UDP {ip}:{port}: {e}.'}
