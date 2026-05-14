# tests/conftest.py
"""
Configuración global de fixtures para pytest
"""
import pytest
import sys
import os
from unittest.mock import MagicMock

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Variables de entorno mínimas para tests (se leen a nivel de clase en config.py)
# DATABASE_URL debe fijarse aquí para que config.py la vea antes de ser importado
# por cualquier módulo de test (ej. test_api_endpoints.py importa 'main' a nivel de módulo).
os.environ.setdefault('SECRET_KEY', 'test_secret')
os.environ.setdefault('ADMIN_PASSWORD', 'admin12345678')
os.environ.setdefault('FIELD_ENCRYPTION_KEY', 'test_field_encryption_key_32bytes!!')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')


@pytest.fixture(scope='session')
def app():
    """Fixture que crea la aplicación Flask para toda la sesión"""
    from main import create_app

    app = create_app()
    app.config['TESTING'] = True
    app.config['DEBUG'] = False
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['RATELIMIT_ENABLED'] = False

    yield app


@pytest.fixture(scope='function')
def client(app):
    """Fixture que crea un cliente de prueba para cada test"""
    return app.test_client()


@pytest.fixture(scope='function')
def mock_powershell():
    """Fixture que mockea send_command_to_powershell"""
    mock = MagicMock()
    mock.return_value = "Mocked PowerShell output"
    return mock


@pytest.fixture(scope='function')
def mock_cache():
    """Fixture que mockea CacheManager"""
    mock = MagicMock()
    mock.is_cache_valid.return_value = False
    mock.get_cached_data.return_value = None
    return mock


@pytest.fixture(scope='session')
def auth_client(app):
    """Cliente autenticado como superadmin — se loguea UNA VEZ por sesión de tests.
    Scope session evita que el rate limiter del login se agote cuando hay muchos tests.
    """
    with app.test_client() as client:
        response = client.post('/auth/login', data={
            'username': 'admin',
            'password': 'admin12345678',
        }, follow_redirects=False)
        assert response.status_code == 302, (
            f"Login falló: status={response.status_code}, body={response.data[:200]!r}"
        )
        yield client


@pytest.fixture
def sample_cpu_output():
    """Fixture con salida de ejemplo de CPU"""
    return "CPU: 45.5%"


@pytest.fixture
def sample_memory_output():
    """Fixture con salida de ejemplo de memoria"""
    return "Memoria: 62.3%"


@pytest.fixture
def sample_disk_output():
    """Fixture con salida de ejemplo de disco"""
    return "Disco usado: 35.5%, Disco libre: 64.5%"


@pytest.fixture
def sample_process_output():
    """Fixture con salida de ejemplo de procesos"""
    return """
Name                       Id CPU
----                       -- ---
chrome.exe               1234 15.5
explorer.exe             5678 3.2
system                      4 0.5
svchost.exe              2345 2.1
"""


@pytest.fixture
def sample_disk_list_output():
    """Fixture con salida de ejemplo de lista de discos"""
    return """
Disco 0 - 256 GB
Estado: En línea
Tipo: SSD

Disco 1 - 1 TB
Estado: En línea
Tipo: HDD
"""


@pytest.fixture
def sample_partition_output():
    """Fixture con salida de ejemplo de particiones"""
    return """
Partición 1
Letra: C:
Tamaño: 100 GB
Sistema: NTFS
Estado: Activo

Partición 2
Letra: D:
Tamaño: 500 GB
Sistema: NTFS
Estado: Activo
"""


# Hooks de pytest para personalizar la salida
def pytest_configure(config):
    """Configuración inicial antes de ejecutar tests"""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )


def pytest_collection_modifyitems(config, items):
    """Modificar items de test después de la recolección"""
    for item in items:
        # Agregar marker 'unit' a tests en directorio unit/
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        # Agregar marker 'integration' a tests en directorio integration/
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
