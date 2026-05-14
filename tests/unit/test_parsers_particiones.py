# tests/unit/test_parsers_particiones.py
"""Tests unitarios para los parsers del módulo de particiones."""
import pytest

from modules.particiones.parsers import (
    parse_physical_disks_output,
    parse_partitions_output,
    parse_disk_detail_output,
    compute_disk_usage_from_partitions,
)


class TestParsePhysicalDisks:
    def test_parsea_un_disco(self):
        text = (
            "Disco 0\n"
            "Modelo: Samsung SSD 970 EVO\n"
            "Tamaño: 500 GB\n"
            "Estado: Bueno\n"
            "Interfaz: NVMe\n"
            "Número de Serie: ABC123\n"
        )
        disks = parse_physical_disks_output(text)
        assert len(disks) == 1
        d = disks[0]
        assert d['id']     == 'disk0'
        assert d['number'] == 0
        assert d['model']  == 'Samsung SSD 970 EVO'
        assert d['size']   == '500 GB'
        assert d['health'] == 'good'
        # Ya no es simulado: arranca a 0 hasta enriquecerse desde particiones
        assert d['usage_percent'] == 0

    def test_parsea_varios_discos(self):
        text = (
            "Disco 0\nModelo: SSD A\nTamaño: 250 GB\nEstado: Bueno\n\n"
            "Disco 1\nModelo: HDD B\nTamaño: 2 TB\nEstado: Bueno\n"
        )
        disks = parse_physical_disks_output(text)
        assert len(disks) == 2
        assert disks[0]['number'] == 0
        assert disks[1]['number'] == 1

    def test_excluye_discos_pequenos(self):
        text = (
            "Disco 0\nModelo: USB Stick\nTamaño: 4 GB\nEstado: Bueno\n"
        )
        disks = parse_physical_disks_output(text)
        # 4 GB < 8 GB → excluido
        assert disks == []

    def test_vacio(self):
        assert parse_physical_disks_output('') == []
        assert parse_physical_disks_output(None) == []


class TestComputeDiskUsageFromPartitions:
    def test_calcula_uso_real(self):
        disks = [{'id': 'disk0', 'number': 0, 'usage_percent': 0}]
        partitions_by_disk = {
            '0': [
                {'size_gb': 100.0, 'used_gb': 50.0, 'free_gb': 50.0},
                {'size_gb': 200.0, 'used_gb': 80.0, 'free_gb': 120.0},
            ]
        }
        compute_disk_usage_from_partitions(disks, partitions_by_disk)
        d = disks[0]
        # 130 / 300 = 43.33%
        assert d['usage_percent'] == pytest.approx(43.3, rel=1e-2)
        assert d['size_total_gb'] == 300.0
        assert d['used_total_gb'] == 130.0
        assert d['free_total_gb'] == 170.0

    def test_disco_sin_particiones(self):
        disks = [{'id': 'disk1', 'number': 1, 'usage_percent': 0}]
        compute_disk_usage_from_partitions(disks, {})
        assert disks[0]['usage_percent'] == 0
        assert disks[0]['size_total_gb'] == 0


class TestParsePartitions:
    def test_parsea_particion_completa(self):
        text = (
            "Partición: 1 (Disco 0)\n"
            "Letra: C:\n"
            "Etiqueta: Sistema\n"
            "Sistema de archivos: NTFS\n"
            "Tamaño: 100 GB\n"
            "Usado: 60%\n"
            "Tipo: Primary\n"
        )
        parts = parse_partitions_output(text)
        assert len(parts) == 1
        p = parts[0]
        assert p['id'] == '0-1'
        assert p['disk_id'] == '0'
        assert p['letter'] == 'C'
        assert p['label']  == 'Sistema'
        assert p['filesystem'] == 'NTFS'
        assert p['size_gb'] == 100.0
        assert p['used_percent'] == 60.0
        assert p['used_gb'] == 60.0
        assert p['free_gb'] == 40.0
        assert p['status'] == 'active'

    def test_descarta_sin_disco(self):
        text = "Letra: D:\nEtiqueta: x\nTamaño: 10 GB\n"
        assert parse_partitions_output(text) == []


class TestParseDiskDetail:
    def test_parsea_detalles(self):
        text = (
            "Disco 0\n"
            "Modelo: Samsung SSD\n"
            "Serial: SN123\n"
            "Interfaz: NVMe\n"
            "Tamaño: 500 GB\n"
            "Particiones: 3\n"
            "Estado: Healthy\n"
            "SMART: Bueno\n"
        )
        d = parse_disk_detail_output(text, 'disk0')
        assert d['model']      == 'Samsung SSD'
        assert d['serial']     == 'SN123'
        assert d['size']       == '500 GB'
        assert d['partitions'] == 3
        assert d['health']     == 'good'
