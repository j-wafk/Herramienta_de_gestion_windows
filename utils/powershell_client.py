# utils/powershell_client.py
import os
import socket
import ssl
import logging
from flask import jsonify
from config import Config

logger = logging.getLogger(__name__)

# TLS opcional: se activa si PS_TLS_ENABLED=true y PS_SERVER_CA_CERT apunta al CA.
_TLS_ENABLED = os.getenv('PS_TLS_ENABLED', 'false').lower() == 'true'
_TLS_CA_CERT = os.getenv('PS_SERVER_CA_CERT', '')

if _TLS_ENABLED:
    logger.info("Comunicación PowerShell en modo TLS")
else:
    logger.warning(
        "Comunicación PowerShell en texto plano. "
        "Configura PS_TLS_ENABLED=true y PS_SERVER_CA_CERT para habilitar TLS."
    )


def _connect(host: str, port: int) -> socket.socket:
    """Crea una conexión TCP (o TLS si está habilitado).

    Connect timeout = SOCKET_TIMEOUT (corto, ~3s) para detectar rápido máquinas
    apagadas y no bloquear la UI. Read timeout = 15s para dar margen a comandos
    PowerShell lentos (process snapshot, ping con 4 paquetes, etc.).
    """
    raw = socket.create_connection((host, port), timeout=Config.SOCKET_TIMEOUT)
    raw.settimeout(15)
    if _TLS_ENABLED and _TLS_CA_CERT:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_verify_locations(cafile=_TLS_CA_CERT)
        return ctx.wrap_socket(raw, server_hostname=host)
    return raw


def _recv_all(sock: socket.socket) -> bytes:
    """Lee hasta que el servidor cierra la conexión o hay timeout."""
    chunks = []
    try:
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
    except socket.timeout:
        pass
    return b''.join(chunks)


def send_command_to_powershell(command: str) -> str:
    """Envía un comando al servidor PowerShell local y devuelve la respuesta."""
    verb = command.split()[0] if command else '<vacío>'
    try:
        logger.debug(f"PS local — verbo: {verb}")
        with _connect(Config.POWERSHELL_SERVER, Config.POWERSHELL_PORT) as s:
            s.sendall(command.encode('utf-8') + b'\n')
            response = _recv_all(s)
        decoded = response.decode('utf-8', errors='replace').strip()
        logger.debug(f"PS local — respuesta: {len(response)} bytes")
        return decoded
    except ConnectionRefusedError:
        logger.error(f"PS local — conexión rechazada (verbo: {verb})")
        return "No se pudo conectar al servidor PowerShell"
    except Exception as e:
        logger.error(f"PS local — error ({type(e).__name__}) para verbo: {verb}")
        return f"Error conectando con PowerShell: {type(e).__name__}"


def send_command_to_machine(command: str, ip: str, port: int) -> str:
    """Envía un comando a un servidor PowerShell remoto (ip:port)."""
    verb = command.split()[0] if command else '<vacío>'
    try:
        logger.debug(f"PS remoto {ip}:{port} — verbo: {verb}")
        with _connect(ip, int(port)) as s:
            s.sendall(command.encode('utf-8') + b'\n')
            response = _recv_all(s)
        decoded = response.decode('utf-8', errors='replace').strip()
        logger.debug(f"PS remoto {ip}:{port} — respuesta: {len(response)} bytes")
        return decoded
    except ConnectionRefusedError:
        logger.error(f"PS remoto — conexión rechazada a {ip}:{port} (verbo: {verb})")
        return f"No se pudo conectar al servidor PowerShell en {ip}:{port}"
    except Exception as e:
        logger.error(f"PS remoto — error ({type(e).__name__}) a {ip}:{port}")
        return f"Error conectando con {ip}:{port}: {type(e).__name__}"


def resolve_and_send(command: str, machine_id=None) -> str:
    """Envía a la máquina indicada por machine_id, o a la local si no se especifica."""
    if machine_id:
        try:
            from database.models import Machine
            machine = Machine.query.get(int(machine_id))
            if machine:
                return send_command_to_machine(command, machine.ip, machine.port)
        except Exception as e:
            logger.warning(f"No se pudo resolver machine_id={machine_id}: {type(e).__name__}")
    return send_command_to_powershell(command)


def health_check_powershell():
    """Verifica el estado del servidor PowerShell."""
    try:
        with _connect(Config.POWERSHELL_SERVER, Config.POWERSHELL_PORT):
            pass
        return jsonify({"status": "ok", "message": "Servidor PowerShell funcionando correctamente"})
    except Exception as e:
        logger.error(f"Health check PowerShell fallido: {type(e).__name__}")
        return jsonify({"status": "error", "message": "No se pudo conectar con el servidor PowerShell"}), 503


class PowerShellClient:
    """Cliente orientado a objetos para comunicarse con un servidor PowerShell TCP.

    Wrapper sobre las funciones de módulo que permite instanciar un cliente
    apuntando a una máquina específica y reutilizarlo en múltiples llamadas.
    Las funciones de módulo (send_command_to_machine, etc.) siguen siendo la
    implementación real; esta clase delega en ellas.

    Ejemplo::

        client = PowerShellClient('192.168.1.10', 12345)
        output = client.send_command('cpu')
    """

    def __init__(self, host: str, port: int, timeout: int = None,
                 tls: bool = False, ca_cert: str = None):
        self.host = host
        self.port = port
        self.timeout = timeout or Config.SOCKET_TIMEOUT
        self.tls = tls      # reservado: actualmente se controla via env PS_TLS_ENABLED
        self.ca_cert = ca_cert  # reservado: actualmente se controla via env PS_SERVER_CA_CERT

    def send_command(self, command: str) -> str:
        """Envía un comando al servidor PowerShell de esta instancia."""
        return send_command_to_machine(command, self.host, self.port)
