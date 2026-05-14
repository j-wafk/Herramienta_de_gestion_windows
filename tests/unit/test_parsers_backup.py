# tests/unit/test_parsers_backup.py
"""Tests unitarios para los parsers del módulo de backup."""
import pytest

from modules.backup.parsers import (
    parse_backup_output,
    parse_backup_list_output,
    parse_compression_output,
    parse_size_output,
    parse_scheduled_tasks_output,
)


class TestParseBackupOutput:
    def test_completo_exitoso(self):
        text = (
            "Backup completado exitosamente\n"
            "Archivos procesados: 1234 archivos copiados\n"
            "Tamaño procesado: 256.5 MB\n"
            "Duración: 45.7 segundos\n"
            "Tipo: full\n"
        )
        r = parse_backup_output(text)
        assert r['success'] is True
        assert r['files_processed'] == 1234
        assert r['size_processed'] == '256.5 MB'
        assert r['duration'] == '45.7 segundos'
        assert r['error'] is None

    def test_error_marca_success_falso(self):
        text = "Backup falló error: La ruta no existe"
        r = parse_backup_output(text)
        assert r['success'] is False
        assert r['error'] is not None
        assert 'no existe' in r['error'].lower()

    def test_error_simple_sin_colon_marca_success_falso(self):
        text = "Error al crear backup: La ruta no existe"
        r = parse_backup_output(text)
        assert r['success'] is False

    def test_vacio_no_revienta(self):
        r = parse_backup_output('')
        assert r['success'] is False


class TestParseBackupListOutput:
    def test_lista_normal(self):
        text = (
            "Nombre | Fecha | Tamaño | Tipo\n"
            "backup_1.zip | 2026-01-10 12:00:00 | 100 MB | full\n"
            "backup_2 | 2026-01-09 10:30:00 | 200 MB | incremental\n"
        )
        items = parse_backup_list_output(text)
        assert len(items) == 2
        # Ordenado por fecha descendente
        assert items[0]['name'] == 'backup_1.zip'
        assert items[0]['size'] == '100 MB'
        assert items[0]['type'] == 'full'

    def test_solo_cabecera_devuelve_vacio(self):
        text = "Nombre | Fecha | Tamaño | Tipo"
        assert parse_backup_list_output(text) == []

    def test_mensaje_sin_backups(self):
        text = "Sin backups\n(La ruta C:\\foo no existe o aun no tiene backups)"
        assert parse_backup_list_output(text) == []

    def test_separador_y_filas(self):
        text = (
            "Nombre | Fecha | Tamaño | Tipo\n"
            "--------\n"
            "x.zip | 2026-01-10 12:00:00 | 1 MB | full\n"
        )
        items = parse_backup_list_output(text)
        assert len(items) == 1
        assert items[0]['name'] == 'x.zip'

    def test_vacio(self):
        assert parse_backup_list_output('') == []
        assert parse_backup_list_output(None) == []


class TestParseCompressionOutput:
    def test_ok(self):
        text = (
            "Compresión completada exitosamente\n"
            "Tamaño original: 500 MB\n"
            "Tamaño comprimido: 200 MB\n"
            "Ratio de compresión: 60%\n"
            "150 archivos comprimidos\n"
        )
        r = parse_compression_output(text)
        assert r['success'] is True
        assert r['original_size'] == '500 MB'
        assert r['compressed_size'] == '200 MB'
        assert r['compression_ratio'] == '60%'
        assert r['files_compressed'] == 150


class TestParseSizeOutput:
    def test_ok(self):
        r = parse_size_output("bytes: 1024\nfiles: 5")
        assert r == {'bytes': 1024, 'files': 5}

    def test_parcial(self):
        r = parse_size_output("bytes: 99")
        assert r == {'bytes': 99, 'files': 0}

    def test_vacio(self):
        assert parse_size_output('') == {'bytes': 0, 'files': 0}


class TestParseScheduledTasksOutput:
    def test_formato_tabular(self):
        text = (
            "task|state|next|last\n"
            "GestionBackup_a|Ready|2026-05-09 02:00:00|2026-05-08 02:00:00\n"
            "GestionBackup_b|Disabled|-|-\n"
        )
        items = parse_scheduled_tasks_output(text)
        assert len(items) == 2
        assert items[0]['task_name'] == 'GestionBackup_a'
        assert items[0]['state'] == 'Ready'
        assert items[0]['next_run'] == '2026-05-09 02:00:00'
        assert items[1]['next_run'] is None
        assert items[1]['last_run'] is None

    def test_formato_legacy_bloques(self):
        text = (
            "Backups programados:\n\n"
            "Tarea: GestionBackup_x\n"
            "Estado: Ready\n"
            "Proxima ejecucion: 2026-05-09 02:00:00\n"
            "Ultima ejecucion: Nunca\n"
        )
        items = parse_scheduled_tasks_output(text)
        assert len(items) == 1
        assert items[0]['task_name'] == 'GestionBackup_x'
        assert items[0]['state'] == 'Ready'
        assert items[0]['last_run'] is None

    def test_solo_cabecera(self):
        assert parse_scheduled_tasks_output('task|state|next|last') == []

    def test_vacio(self):
        assert parse_scheduled_tasks_output('') == []
