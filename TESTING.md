# Guía de Testing - Herramienta de Gestión Remota

Esta guía explica cómo ejecutar y mantener los tests automatizados del proyecto.

## Tabla de Contenidos

1. [Instalación](#instalación)
2. [Estructura de Tests](#estructura-de-tests)
3. [Ejecutar Tests](#ejecutar-tests)
4. [Tipos de Tests](#tipos-de-tests)
5. [Coverage (Cobertura)](#coverage-cobertura)
6. [Escribir Nuevos Tests](#escribir-nuevos-tests)
7. [Mejores Prácticas](#mejores-prácticas)
8. [CI/CD Integration](#cicd-integration)

## Instalación

### Instalar Dependencias de Testing

```bash
pip install -r requirements-dev.txt
```

Esto instalará:
- **pytest**: Framework de testing
- **pytest-cov**: Plugin de coverage
- **pytest-mock**: Mocking utilities
- **pytest-flask**: Testing para Flask
- **responses**: Mock de requests HTTP
- Y otras herramientas de calidad de código

## Estructura de Tests

```
tests/
├── __init__.py
├── conftest.py                      # Fixtures globales
├── unit/                            # Tests unitarios
│   ├── __init__.py
│   ├── test_parsers_rendimiento.py # Tests de parsers
│   └── test_cache_manager.py       # Tests de caché
├── integration/                     # Tests de integración
│   ├── __init__.py
│   └── test_api_endpoints.py       # Tests de API
└── fixtures/                        # Datos de prueba
```

### Archivos de Configuración

- **pytest.ini**: Configuración principal de pytest
- **conftest.py**: Fixtures compartidas entre tests
- **.coveragerc**: Configuración de coverage (en pytest.ini)

## Ejecutar Tests

### Usando Scripts Automatizados

#### Windows
```bash
run_tests.bat
```

#### Linux/Mac
```bash
chmod +x run_tests.sh
./run_tests.sh
```

Ambos scripts ofrecen un menú interactivo con opciones:
1. Todos los tests
2. Solo tests unitarios
3. Solo tests de integración
4. Tests con coverage detallado
5. Tests rápidos (sin coverage)
6. Tests de módulo específico
7. Generar reporte HTML
8. Limpiar archivos de test

### Comandos Manuales con pytest

#### Ejecutar todos los tests
```bash
pytest
```

#### Ejecutar con verbose (-v)
```bash
pytest -v
```

#### Ejecutar solo tests unitarios
```bash
pytest tests/unit/ -v
```

#### Ejecutar solo tests de integración
```bash
pytest tests/integration/ -v
```

#### Ejecutar un archivo específico
```bash
pytest tests/unit/test_cache_manager.py -v
```

#### Ejecutar un test específico
```bash
pytest tests/unit/test_cache_manager.py::TestCacheManager::test_cache_initialization -v
```

#### Ejecutar tests por marker
```bash
pytest -m unit          # Solo unitarios
pytest -m integration   # Solo integración
pytest -m "not slow"    # Excluir tests lentos
```

#### Ejecutar tests con palabra clave
```bash
pytest -k cache         # Tests con "cache" en el nombre
pytest -k "not api"     # Excluir tests con "api"
```

#### Parar en el primer fallo (-x)
```bash
pytest -x
```

#### Mostrar print statements (-s)
```bash
pytest -s
```

## Tipos de Tests

### Tests Unitarios

Tests que verifican componentes individuales aisladamente.

**Ubicación**: `tests/unit/`

**Ejemplo**:
```python
def test_parse_cpu_valid_output():
    output = "CPU: 45.5%"
    result = parse_cpu_output(output)
    assert result == 45.5
```

**Características**:
- Rápidos de ejecutar (< 1 segundo)
- No dependen de servicios externos
- Usan mocks para dependencias
- Alta cobertura de casos edge

### Tests de Integración

Tests que verifican la interacción entre componentes.

**Ubicación**: `tests/integration/`

**Ejemplo**:
```python
def test_system_endpoint_with_cached_data(client, mock_cache):
    mock_cache.is_cache_valid.return_value = True
    response = client.get('/api/system')
    assert response.status_code == 200
```

**Características**:
- Más lentos que unitarios
- Pueden usar base de datos de test
- Verifican flujos completos
- Mockean solo servicios externos (PowerShell)

### Markers Disponibles

- `@pytest.mark.unit`: Test unitario
- `@pytest.mark.integration`: Test de integración
- `@pytest.mark.slow`: Test que tarda más de 5 segundos
- `@pytest.mark.api`: Test de endpoint API
- `@pytest.mark.parsers`: Test de parsers
- `@pytest.mark.cache`: Test de caché
- `@pytest.mark.backup`: Test de backup
- `@pytest.mark.partitions`: Test de particiones

## Coverage (Cobertura)

### Generar Reporte de Coverage

```bash
pytest --cov=modules --cov=utils --cov=main --cov-report=html
```

### Ver Reporte en el Terminal

```bash
pytest --cov=modules --cov=utils --cov=main --cov-report=term-missing
```

Esto mostrará:
- Porcentaje de cobertura por archivo
- Líneas específicas no cubiertas

### Abrir Reporte HTML

El reporte HTML se genera en `htmlcov/index.html`:

```bash
# Windows
start htmlcov/index.html

# Linux
xdg-open htmlcov/index.html

# Mac
open htmlcov/index.html
```

### Interpretar Cobertura

- **Verde (80-100%)**: Excelente cobertura
- **Amarillo (60-79%)**: Cobertura aceptable
- **Rojo (0-59%)**: Necesita más tests

### Objetivo de Coverage

- **Mínimo aceptable**: 70%
- **Objetivo**: 80%
- **Ideal**: 90%+

Archivos críticos (parsers, API routes) deben tener 90%+ coverage.

## Escribir Nuevos Tests

### Template para Test Unitario

```python
# tests/unit/test_mi_modulo.py
import pytest
from mi_modulo import mi_funcion


class TestMiFuncion:
    """Tests para mi_funcion"""

    def test_caso_normal(self):
        """Test con entrada válida"""
        resultado = mi_funcion("entrada")
        assert resultado == "salida_esperada"

    def test_caso_edge(self):
        """Test con caso límite"""
        resultado = mi_funcion("")
        assert resultado == ""

    def test_caso_error(self):
        """Test que verifica manejo de errores"""
        with pytest.raises(ValueError):
            mi_funcion(None)
```

### Template para Test de Integración

```python
# tests/integration/test_mi_endpoint.py
import pytest
from unittest.mock import patch


class TestMiEndpoint:
    """Tests para /api/mi-endpoint"""

    @pytest.fixture
    def client(self, app):
        return app.test_client()

    @patch('mi_modulo.dependencia_externa')
    def test_endpoint_success(self, mock_dep, client):
        """Test de endpoint exitoso"""
        mock_dep.return_value = "valor_mock"

        response = client.get('/api/mi-endpoint')

        assert response.status_code == 200
        assert 'esperado' in response.json
```

### Usando Fixtures

Las fixtures están definidas en `tests/conftest.py`:

```python
def test_con_fixture(client, mock_powershell, sample_cpu_output):
    """Test usando fixtures predefinidas"""
    mock_powershell.return_value = sample_cpu_output
    response = client.get('/api/system')
    assert response.status_code == 200
```

### Fixtures Disponibles

- `app`: Aplicación Flask configurada
- `client`: Cliente de prueba Flask
- `mock_powershell`: Mock de send_command_to_powershell
- `mock_cache`: Mock de CacheManager
- `sample_cpu_output`: Salida de ejemplo de CPU
- `sample_memory_output`: Salida de ejemplo de memoria
- `sample_disk_output`: Salida de ejemplo de disco
- `sample_process_output`: Salida de ejemplo de procesos

## Mejores Prácticas

### 1. Nombrado de Tests

- **Descriptivo**: `test_parse_cpu_with_valid_output`
- **No genérico**: ~~`test_1`~~
- Usar `test_` como prefijo obligatorio

### 2. Estructura AAA (Arrange-Act-Assert)

```python
def test_ejemplo():
    # Arrange: Preparar datos
    input_data = "test"

    # Act: Ejecutar función
    result = funcion_bajo_test(input_data)

    # Assert: Verificar resultado
    assert result == "expected"
```

### 3. Un Assert por Test

```python
# Bien
def test_cpu_value():
    result = parse_cpu("CPU: 50%")
    assert result == 50.0

def test_cpu_format():
    result = parse_cpu("CPU: 50%")
    assert isinstance(result, float)

# Mal
def test_cpu():
    result = parse_cpu("CPU: 50%")
    assert result == 50.0
    assert isinstance(result, float)
    assert result > 0
```

### 4. Tests Independientes

Cada test debe poder ejecutarse de forma aislada:

```python
# Bien
def test_cache_set():
    cache = CacheManager()
    cache.set("key", "value")
    assert cache.get("key") == "value"

# Mal (depende de estado global)
cache = CacheManager()

def test_cache_set():
    cache.set("key", "value")

def test_cache_get():
    # Falla si test_cache_set no se ejecutó antes
    assert cache.get("key") == "value"
```

### 5. Mocking Apropiado

Mockear solo lo necesario:

```python
@patch('utils.powershell_client.send_command_to_powershell')
def test_api_endpoint(mock_ps, client):
    mock_ps.return_value = "CPU: 50%"
    response = client.get('/api/system')
    assert response.status_code == 200
```

### 6. Tests Legibles

```python
# Bien
def test_disk_parser_returns_correct_percentages():
    """
    Dado: Una salida válida de diskpart
    Cuando: Se parsea el disco
    Entonces: Debe retornar porcentajes correctos
    """
    output = "Disco usado: 35%, Disco libre: 65%"
    result = parse_disk_output(output)

    assert result['used'] == 35.0
    assert result['free'] == 65.0
```

### 7. Coverage ≠ Calidad

No perseguir 100% de coverage a ciegas:
- Algunos bloques son difíciles de testear (error handling)
- Enfocarse en funciones críticas primero
- 90% coverage con tests de calidad > 100% coverage con tests malos

## CI/CD Integration

### GitHub Actions

Crear `.github/workflows/tests.yml`:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: windows-latest

    steps:
    - uses: actions/checkout@v2

    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.9'

    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install -r requirements-dev.txt

    - name: Run tests with coverage
      run: |
        pytest --cov=modules --cov=utils --cov=main --cov-report=xml

    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v2
      with:
        file: ./coverage.xml
```

### Pre-commit Hooks

Instalar pre-commit:

```bash
pip install pre-commit
```

Crear `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: pytest-check
        name: pytest-check
        entry: pytest
        language: system
        pass_filenames: false
        always_run: true
```

Activar:

```bash
pre-commit install
```

Ahora los tests se ejecutarán automáticamente antes de cada commit.

## Comandos Útiles

### Ejecutar tests en paralelo (más rápido)

```bash
pip install pytest-xdist
pytest -n auto
```

### Ver tests más lentos

```bash
pytest --durations=10
```

### Ejecutar solo tests que fallaron

```bash
pytest --lf
```

### Modo watch (re-ejecutar al cambiar archivos)

```bash
pip install pytest-watch
ptw
```

### Generar reporte JUnit (para CI)

```bash
pytest --junit-xml=report.xml
```

## Troubleshooting

### "ModuleNotFoundError"

Asegurarse de estar en el directorio raíz del proyecto:

```bash
cd /ruta/al/proyecto
pytest
```

### Tests pasan localmente pero fallan en CI

- Verificar versiones de dependencias
- Verificar diferencias de sistema operativo
- Revisar que no haya dependencias de archivos locales

### Mocks no funcionan

Verificar la ruta completa en el patch:

```python
# Correcto
@patch('modules.rendimiento.routes.send_command_to_powershell')

# Incorrecto
@patch('send_command_to_powershell')
```

### Coverage no se genera

Verificar que pytest-cov está instalado:

```bash
pip install pytest-cov
```

## Recursos Adicionales

- [Documentación oficial de pytest](https://docs.pytest.org/)
- [pytest-cov documentation](https://pytest-cov.readthedocs.io/)
- [Flask testing guide](https://flask.palletsprojects.com/en/latest/testing/)
- [Python unittest.mock guide](https://docs.python.org/3/library/unittest.mock.html)

## Contacto y Soporte

Para preguntas o problemas con los tests, abrir un issue en el repositorio del proyecto.

---

**Última actualización**: 2024-01-08
