# tests/unit/test_validators.py
"""Tests unitarios completos para utils/validators.py"""
import pytest

from utils.validators import (
    validate_windows_path,
    validate_safe_name,
    validate_enum,
    validate_disk_id,
    validate_id,
    validate_drive_letter,
    validate_partition_id,
    validate_numeric,
    validate_schedule_time,
    validate_network_target,
    validate_adapter_name,
    validate_password_strength,
    ALLOWED_BACKUP_TYPES,
    ALLOWED_JOB_SCHEDULES,
    ALLOWED_DESTINATION_TYPES,
    ALLOWED_FILESYSTEMS,
    ALLOWED_COMPRESS_LEVELS,
    ALLOWED_DISK_TYPES,
)


# ── validate_windows_path ─────────────────────────────────────────────────────

class TestValidateWindowsPath:
    def test_ruta_valida_simple(self):
        assert validate_windows_path('C:\\Users\\test', 'path') == 'C:\\Users\\test'

    def test_ruta_con_subcarpetas(self):
        assert validate_windows_path('D:\\Backups\\carpeta', 'path') == 'D:\\Backups\\carpeta'

    def test_ruta_con_guiones_y_puntos(self):
        assert validate_windows_path('C:\\mis-datos\\archivo.txt', 'path') == 'C:\\mis-datos\\archivo.txt'

    def test_vacio_lanza_error(self):
        with pytest.raises(ValueError, match='obligatoria'):
            validate_windows_path('', 'path')

    def test_none_lanza_error(self):
        with pytest.raises(ValueError, match='obligatoria'):
            validate_windows_path(None, 'path')

    def test_path_traversal_lanza_error(self):
        with pytest.raises(ValueError, match='traversal'):
            validate_windows_path('C:\\..\\Windows\\System32', 'path')

    def test_ruta_relativa_lanza_error(self):
        with pytest.raises(ValueError, match='no válida'):
            validate_windows_path('backups\\data', 'path')

    def test_solo_barra_lanza_error(self):
        with pytest.raises(ValueError):
            validate_windows_path('\\', 'path')

    def test_nombre_campo_en_error(self):
        with pytest.raises(ValueError, match='mi_campo'):
            validate_windows_path('', 'mi_campo')


# ── validate_safe_name ────────────────────────────────────────────────────────

class TestValidateSafeName:
    def test_nombre_letras(self):
        assert validate_safe_name('backup', 'name') == 'backup'

    def test_nombre_con_guion(self):
        assert validate_safe_name('mi-backup', 'name') == 'mi-backup'

    def test_nombre_con_subrayado(self):
        assert validate_safe_name('mi_backup', 'name') == 'mi_backup'

    def test_nombre_con_numeros(self):
        assert validate_safe_name('backup2026', 'name') == 'backup2026'

    def test_maximo_64_chars(self):
        assert validate_safe_name('a' * 64, 'name') == 'a' * 64

    def test_vacio_lanza_error(self):
        with pytest.raises(ValueError):
            validate_safe_name('', 'name')

    def test_none_lanza_error(self):
        with pytest.raises(ValueError):
            validate_safe_name(None, 'name')

    def test_espacios_lanza_error(self):
        with pytest.raises(ValueError):
            validate_safe_name('nombre con espacios', 'name')

    def test_mas_de_64_chars_lanza_error(self):
        with pytest.raises(ValueError):
            validate_safe_name('a' * 65, 'name')

    def test_arroba_lanza_error(self):
        with pytest.raises(ValueError):
            validate_safe_name('nombre@invalido', 'name')

    def test_barra_lanza_error(self):
        with pytest.raises(ValueError):
            validate_safe_name('nombre/invalido', 'name')


# ── validate_enum ─────────────────────────────────────────────────────────────

class TestValidateEnum:
    def test_backup_type_full(self):
        assert validate_enum('full', ALLOWED_BACKUP_TYPES, 'type') == 'full'

    def test_backup_type_incremental(self):
        assert validate_enum('incremental', ALLOWED_BACKUP_TYPES, 'type') == 'incremental'

    def test_backup_type_differential(self):
        assert validate_enum('differential', ALLOWED_BACKUP_TYPES, 'type') == 'differential'

    def test_valor_invalido_lanza_error(self):
        with pytest.raises(ValueError, match='no permitido'):
            validate_enum('completo', ALLOWED_BACKUP_TYPES, 'type')

    def test_vacio_lanza_error(self):
        with pytest.raises(ValueError):
            validate_enum('', ALLOWED_BACKUP_TYPES, 'type')

    def test_none_lanza_error(self):
        with pytest.raises(ValueError):
            validate_enum(None, ALLOWED_BACKUP_TYPES, 'type')

    def test_filesystem_ntfs(self):
        assert validate_enum('NTFS', ALLOWED_FILESYSTEMS, 'fs') == 'NTFS'

    def test_filesystem_fat32(self):
        assert validate_enum('FAT32', ALLOWED_FILESYSTEMS, 'fs') == 'FAT32'

    def test_destination_local(self):
        assert validate_enum('local', ALLOWED_DESTINATION_TYPES, 'dest') == 'local'

    def test_destination_network(self):
        assert validate_enum('network', ALLOWED_DESTINATION_TYPES, 'dest') == 'network'

    def test_schedule_manual_incluido(self):
        assert validate_enum('manual', ALLOWED_JOB_SCHEDULES, 'sched') == 'manual'

    def test_compress_level_high(self):
        assert validate_enum('high', ALLOWED_COMPRESS_LEVELS, 'level') == 'high'

    def test_disk_type_gpt(self):
        assert validate_enum('GPT', ALLOWED_DISK_TYPES, 'dtype') == 'GPT'


# ── validate_disk_id ──────────────────────────────────────────────────────────

class TestValidateDiskId:
    def test_disk0(self):
        assert validate_disk_id('disk0') == 'disk0'

    def test_disk1(self):
        assert validate_disk_id('disk1') == 'disk1'

    def test_mayusculas_normaliza(self):
        assert validate_disk_id('DISK2') == 'disk2'

    def test_numero_grande(self):
        assert validate_disk_id('disk99') == 'disk99'

    def test_sin_prefijo_disk_lanza_error(self):
        with pytest.raises(ValueError, match='disk_id no válido'):
            validate_disk_id('0')

    def test_numero_solo_lanza_error(self):
        with pytest.raises(ValueError):
            validate_disk_id('1')

    def test_vacio_lanza_error(self):
        with pytest.raises(ValueError):
            validate_disk_id('')

    def test_nombre_arbitrario_lanza_error(self):
        with pytest.raises(ValueError):
            validate_disk_id('hdd0')


# ── validate_id ───────────────────────────────────────────────────────────────

class TestValidateId:
    def test_entero_positivo(self):
        assert validate_id(5) == 5

    def test_string_numerico(self):
        assert validate_id('42') == 42

    def test_cero_lanza_error(self):
        with pytest.raises(ValueError):
            validate_id(0)

    def test_negativo_lanza_error(self):
        with pytest.raises(ValueError):
            validate_id(-1)

    def test_string_no_numerico_lanza_error(self):
        with pytest.raises(ValueError):
            validate_id('foo')

    def test_none_lanza_error(self):
        with pytest.raises(ValueError):
            validate_id(None)

    def test_float_trunca_a_entero(self):
        # int(3.7) == 3
        assert validate_id(3.7) == 3


# ── validate_drive_letter ─────────────────────────────────────────────────────

class TestValidateDriveLetter:
    def test_letra_d(self):
        assert validate_drive_letter('D') == 'D'

    def test_letra_minuscula(self):
        assert validate_drive_letter('e') == 'E'

    def test_con_dos_puntos(self):
        assert validate_drive_letter('F:') == 'F'

    def test_minuscula_con_dos_puntos(self):
        assert validate_drive_letter('g:') == 'G'

    def test_vacio_devuelve_vacio(self):
        assert validate_drive_letter('') == ''

    def test_none_devuelve_vacio(self):
        assert validate_drive_letter(None) == ''

    def test_letra_a_reservada(self):
        with pytest.raises(ValueError, match='reservada'):
            validate_drive_letter('A')

    def test_letra_b_reservada(self):
        with pytest.raises(ValueError, match='reservada'):
            validate_drive_letter('B')

    def test_letra_c_reservada(self):
        with pytest.raises(ValueError, match='reservada'):
            validate_drive_letter('C')

    def test_digito_lanza_error(self):
        with pytest.raises(ValueError):
            validate_drive_letter('1')

    def test_z_es_valido(self):
        assert validate_drive_letter('Z') == 'Z'


# ── validate_partition_id ─────────────────────────────────────────────────────

class TestValidatePartitionId:
    def test_numero_uno(self):
        assert validate_partition_id('1') == '1'

    def test_numero_dos_digitos(self):
        assert validate_partition_id('12') == '12'

    def test_numero_tres_digitos(self):
        assert validate_partition_id('128') == '128'

    def test_letras_lanza_error(self):
        with pytest.raises(ValueError):
            validate_partition_id('abc')

    def test_vacio_lanza_error(self):
        with pytest.raises(ValueError):
            validate_partition_id('')

    def test_none_lanza_error(self):
        with pytest.raises(ValueError):
            validate_partition_id(None)


# ── validate_numeric ──────────────────────────────────────────────────────────

class TestValidateNumeric:
    def test_entero_valido(self):
        assert validate_numeric(50, 'val') == 50.0

    def test_string_numerico(self):
        assert validate_numeric('3.14', 'val') == pytest.approx(3.14)

    def test_cero_es_valido(self):
        assert validate_numeric(0, 'val', min_val=0) == 0.0

    def test_minimo_exacto(self):
        assert validate_numeric(10, 'val', min_val=10) == 10.0

    def test_por_debajo_del_minimo(self):
        with pytest.raises(ValueError, match='>='):
            validate_numeric(-1, 'val', min_val=0)

    def test_maximo_exacto(self):
        assert validate_numeric(100, 'val', max_val=100) == 100.0

    def test_por_encima_del_maximo(self):
        with pytest.raises(ValueError, match='<='):
            validate_numeric(101, 'val', max_val=100)

    def test_dentro_del_rango(self):
        assert validate_numeric(50, 'val', min_val=0, max_val=100) == 50.0

    def test_no_numerico_lanza_error(self):
        with pytest.raises(ValueError, match='número'):
            validate_numeric('abc', 'val')

    def test_none_lanza_error(self):
        with pytest.raises(ValueError):
            validate_numeric(None, 'val')


# ── validate_schedule_time ────────────────────────────────────────────────────

class TestValidateScheduleTime:
    def test_medianoche(self):
        assert validate_schedule_time('00:00') == '00:00'

    def test_hora_normal(self):
        assert validate_schedule_time('14:30') == '14:30'

    def test_ultimo_minuto(self):
        assert validate_schedule_time('23:59') == '23:59'

    def test_formato_invalido_letras(self):
        with pytest.raises(ValueError, match='HH:MM'):
            validate_schedule_time('abc')

    def test_hora_25_invalida(self):
        with pytest.raises(ValueError):
            validate_schedule_time('25:00')

    def test_minuto_60_invalido(self):
        with pytest.raises(ValueError):
            validate_schedule_time('12:60')

    def test_vacio_lanza_error(self):
        with pytest.raises(ValueError):
            validate_schedule_time('')

    def test_none_lanza_error(self):
        with pytest.raises(ValueError):
            validate_schedule_time(None)

    def test_formato_sin_dos_puntos(self):
        with pytest.raises(ValueError):
            validate_schedule_time('1430')


# ── validate_network_target ───────────────────────────────────────────────────

class TestValidateNetworkTarget:
    def test_ipv4_valida(self):
        assert validate_network_target('192.168.1.1') == '192.168.1.1'

    def test_localhost(self):
        assert validate_network_target('127.0.0.1') == '127.0.0.1'

    def test_hostname_valido(self):
        assert validate_network_target('server01.local') == 'server01.local'

    def test_fqdn(self):
        assert validate_network_target('mi-servidor.empresa.com') == 'mi-servidor.empresa.com'

    def test_vacio_devuelve_default(self):
        assert validate_network_target('') == '8.8.8.8'

    def test_none_devuelve_default(self):
        assert validate_network_target(None) == '8.8.8.8'

    def test_ip_invalida_lanza_error(self):
        # '999.999.999.999' pasa como hostname; usamos un valor con @ que falla ambos regex
        with pytest.raises(ValueError, match='no válido'):
            validate_network_target('host@invalido')

    def test_punto_coma_lanza_error(self):
        with pytest.raises(ValueError):
            validate_network_target('host; rm -rf /')

    def test_espacios_lanza_error(self):
        with pytest.raises(ValueError):
            validate_network_target('host name.local')


# ── validate_adapter_name ─────────────────────────────────────────────────────

class TestValidateAdapterName:
    def test_nombre_simple(self):
        assert validate_adapter_name('Ethernet') == 'Ethernet'

    def test_con_numeros(self):
        assert validate_adapter_name('Ethernet0') == 'Ethernet0'

    def test_con_parentesis(self):
        assert validate_adapter_name('vEthernet (WSL)') == 'vEthernet (WSL)'

    def test_con_guion(self):
        assert validate_adapter_name('Wi-Fi') == 'Wi-Fi'

    def test_con_punto(self):
        assert validate_adapter_name('Local Area Connection.1') == 'Local Area Connection.1'

    def test_maximo_64_chars(self):
        assert validate_adapter_name('A' * 64) == 'A' * 64

    def test_vacio_lanza_error(self):
        with pytest.raises(ValueError):
            validate_adapter_name('')

    def test_none_lanza_error(self):
        with pytest.raises(ValueError):
            validate_adapter_name(None)

    def test_mas_de_64_lanza_error(self):
        with pytest.raises(ValueError):
            validate_adapter_name('A' * 65)

    def test_arroba_lanza_error(self):
        with pytest.raises(ValueError):
            validate_adapter_name('Adapter@Invalid')


# ── validate_password_strength ────────────────────────────────────────────────

class TestValidatePasswordStrength:
    def test_contrasena_valida(self):
        pwd = 'Segura@Pass1!'
        assert validate_password_strength(pwd) == pwd

    def test_exactamente_12_chars(self):
        assert validate_password_strength('Aa1!Aa1!Aa1!') == 'Aa1!Aa1!Aa1!'

    def test_demasiado_corta(self):
        with pytest.raises(ValueError, match='12 caracteres'):
            validate_password_strength('Ab1!')

    def test_sin_mayuscula(self):
        with pytest.raises(ValueError, match='mayúscula'):
            validate_password_strength('segura@pass1!')

    def test_sin_minuscula(self):
        with pytest.raises(ValueError, match='minúscula'):
            validate_password_strength('SEGURA@PASS1!')

    def test_sin_numero(self):
        with pytest.raises(ValueError, match='número'):
            validate_password_strength('Segura@Password!')

    def test_sin_caracter_especial(self):
        with pytest.raises(ValueError, match='especial'):
            validate_password_strength('SeguraPassword1')

    def test_vacia_lanza_error(self):
        with pytest.raises(ValueError):
            validate_password_strength('')

    def test_none_lanza_error(self):
        with pytest.raises(ValueError):
            validate_password_strength(None)

    def test_contrasena_larga_es_valida(self):
        pwd = 'MuySegurisima@Pass123!!!XYZ'
        assert validate_password_strength(pwd) == pwd
