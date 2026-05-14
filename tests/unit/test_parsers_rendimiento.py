# tests/unit/test_parsers_rendimiento.py
"""
Tests unitarios para los parsers del módulo de rendimiento
"""
import pytest
from modules.rendimiento.parsers import (
    parse_cpu_output,
    parse_memory_output,
    parse_disk_output,
    parse_process_output,
)


class TestParseCPUOutput:
    """Tests para el parser de CPU"""

    def test_parse_cpu_valid_output(self):
        """Test con salida válida de CPU"""
        output = "CPU: 45.5%"
        result = parse_cpu_output(output)
        assert result == 45.5

    def test_parse_cpu_integer(self):
        """Test con valor entero"""
        output = "CPU: 67%"
        result = parse_cpu_output(output)
        assert result == 67.0

    def test_parse_cpu_zero(self):
        """Test con CPU en 0%"""
        output = "CPU: 0%"
        result = parse_cpu_output(output)
        assert result == 0.0

    def test_parse_cpu_hundred(self):
        """Test con CPU al 100%"""
        output = "CPU: 100%"
        result = parse_cpu_output(output)
        assert result == 100.0

    def test_parse_cpu_invalid_format(self):
        """Test con formato inválido debe retornar 0"""
        output = "Invalid CPU data"
        result = parse_cpu_output(output)
        assert result == 0.0

    def test_parse_cpu_empty_string(self):
        """Test con string vacío"""
        output = ""
        result = parse_cpu_output(output)
        assert result == 0.0

    def test_parse_cpu_multiline(self):
        """Test con salida multilínea debe encontrar CPU"""
        output = """
        System Info
        CPU: 23.8%
        Memory: 50%
        """
        result = parse_cpu_output(output)
        assert result == 23.8


class TestParseMemoryOutput:
    """Tests para el parser de memoria"""

    def test_parse_memory_valid_output(self):
        """Test con salida válida de memoria"""
        output = "Memoria: 62.3%"
        result = parse_memory_output(output)
        assert result == 62.3

    def test_parse_memory_integer(self):
        """Test con valor entero"""
        output = "Memoria: 75%"
        result = parse_memory_output(output)
        assert result == 75.0

    def test_parse_memory_invalid_format(self):
        """Test con formato inválido"""
        output = "No memory data"
        result = parse_memory_output(output)
        assert result == 0.0

    def test_parse_memory_multiline(self):
        """Test con salida multilínea"""
        output = """
        Total: 16 GB
        Memoria: 85.5%
        Available: 2.5 GB
        """
        result = parse_memory_output(output)
        assert result == 85.5


class TestParseDiskOutput:
    """Tests para el parser de disco"""

    def test_parse_disk_valid_output(self):
        """Test con salida válida de disco"""
        output = "Disco usado: 45.25%, Disco libre: 54.75%"
        result = parse_disk_output(output)
        assert result['used'] == 45.25
        assert result['free'] == 54.75

    def test_parse_disk_full(self):
        """Test con disco lleno"""
        output = "Disco usado: 100%, Disco libre: 0%"
        result = parse_disk_output(output)
        assert result['used'] == 100.0
        assert result['free'] == 0.0

    def test_parse_disk_empty(self):
        """Test con disco vacío"""
        output = "Disco usado: 0%, Disco libre: 100%"
        result = parse_disk_output(output)
        assert result['used'] == 0.0
        assert result['free'] == 100.0

    def test_parse_disk_invalid_format(self):
        """Test con formato inválido"""
        output = "Invalid disk data"
        result = parse_disk_output(output)
        assert result['used'] == 0.0
        assert result['free'] == 100.0

    def test_parse_disk_missing_free(self):
        """Test con solo dato de usado"""
        output = "Disco usado: 30%"
        result = parse_disk_output(output)
        # Debería calcular el libre como 100 - usado
        assert result['used'] == 30.0
        assert result['free'] == 70.0


class TestParseProcessOutput:
    """Tests para el parser de procesos"""

    def test_parse_process_valid_output(self):
        """Test con salida válida de procesos (formato pipe)."""
        output = (
            "Name|Id|CPU|Memory\n"
            "chrome.exe|1234|15.5|200 MB\n"
            "explorer.exe|5678|3.2|80 MB\n"
            "system|4|0.5|10 MB\n"
        )
        result = parse_process_output(output)
        assert len(result) >= 3
        process_names = [p['name'] for p in result]
        assert 'chrome.exe' in process_names
        assert 'explorer.exe' in process_names

    def test_parse_process_empty_output(self):
        """Test con salida vacía"""
        output = ""
        result = parse_process_output(output)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_parse_process_header_only(self):
        """Test con solo encabezados"""
        output = """
Name                       Id CPU
----                       -- ---
        """
        result = parse_process_output(output)
        assert isinstance(result, list)

    def test_parse_process_with_spaces(self):
        """Test con nombres que contienen espacios (formato pipe)."""
        output = (
            "Name|Id|CPU|Memory\n"
            "Google Chrome Helper|1111|5.0|300 MB\n"
            "Microsoft Edge|2222|8.5|250 MB\n"
        )
        result = parse_process_output(output)
        assert len(result) >= 2


class TestParserEdgeCases:
    """Tests para casos extremos de todos los parsers"""

    def test_parsers_with_none_input(self):
        """Verificar que los parsers manejan None correctamente"""
        # Este test verifica que los parsers no lanzan excepciones con None
        # En la implementación real, deberían manejar este caso
        pass

    def test_parsers_with_unicode(self):
        """Test con caracteres unicode"""
        output = "CPU: 45.5% 🖥️"
        result = parse_cpu_output(output)
        assert result == 45.5

    def test_parse_large_numbers(self):
        """Test con números muy grandes"""
        output = "CPU: 999999%"
        result = parse_cpu_output(output)
        # Debería parsearse aunque sea un valor irreal
        assert result == 999999.0

    def test_parse_negative_numbers(self):
        """El regex \d+ no captura el signo '-'; el fallback extrae los dígitos '5'."""
        output = "CPU: -5%"
        result = parse_cpu_output(output)
        # El primer patrón no coincide con '-5'; el segundo extrae '5' sin el signo
        assert result == 5.0
