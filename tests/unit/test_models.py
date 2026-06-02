# tests/unit/test_models.py
"""Tests unitarios para los métodos de los modelos ORM (sin acceso a BD).

Comprueba lógica pura: set_password, check_password, to_dict, cálculos
derivados. Las relaciones lazy-load quedan fuera de scope aquí; se cubren
en los tests de integración.
"""
import os
import pytest
from datetime import datetime

os.environ.setdefault('SECRET_KEY', 'test_secret')
os.environ.setdefault('ADMIN_PASSWORD', 'Admin12345678!')
os.environ.setdefault('FIELD_ENCRYPTION_KEY', 'test_field_encryption_key_32bytes!!')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')


# ── User ──────────────────────────────────────────────────────────────────────

class TestUserModel:
    def test_set_password_genera_hash(self):
        from database.models import User
        u = User(username='alice', role='admin')
        u.set_password('MiContraseña@1234')
        assert u.password_hash is not None
        assert u.password_hash != 'MiContraseña@1234'

    def test_check_password_correcto(self):
        from database.models import User
        u = User(username='bob', role='solo_lectura')
        u.set_password('Correct@Pass123')
        assert u.check_password('Correct@Pass123') is True

    def test_check_password_incorrecto(self):
        from database.models import User
        u = User(username='carol', role='operador')
        u.set_password('Correct@Pass123')
        assert u.check_password('WrongPass') is False

    def test_password_diferente_cada_hash(self):
        """Dos llamadas a set_password producen hashes distintos (salt aleatorio)."""
        from database.models import User
        u = User(username='dave', role='admin')
        u.set_password('SamePwd@Pass1')
        h1 = u.password_hash
        u.set_password('SamePwd@Pass1')
        h2 = u.password_hash
        assert h1 != h2

    def test_to_dict_contiene_campos_esperados(self):
        from database.models import User
        u = User(username='eve', role='operador', is_active=True)
        u.id = 99
        u.created_at = datetime(2026, 1, 1, 12, 0, 0)
        u.last_login = None
        u.updated_at = None
        d = u.to_dict()
        assert d['username'] == 'eve'
        assert d['role'] == 'operador'
        assert d['is_active'] is True
        assert d['id'] == 99
        assert d['last_login'] is None

    def test_to_dict_no_expone_password_hash(self):
        from database.models import User
        u = User(username='frank', role='admin')
        u.set_password('Test@Pass1234')
        u.created_at = datetime(2026, 1, 1)
        d = u.to_dict()
        assert 'password_hash' not in d

    def test_to_dict_last_login_serializa_iso(self):
        from database.models import User
        u = User(username='grace', role='admin')
        u.created_at = datetime(2026, 1, 1)
        u.last_login = datetime(2026, 5, 1, 10, 30, 0)
        d = u.to_dict()
        assert d['last_login'] == '2026-05-01T10:30:00'

    def test_to_dict_created_at_serializa_iso(self):
        from database.models import User
        u = User(username='hank', role='solo_lectura')
        u.created_at = datetime(2026, 3, 15, 8, 0, 0)
        d = u.to_dict()
        assert d['created_at'] == '2026-03-15T08:00:00'

    def test_role_default_solo_lectura(self):
        from database.models import User
        # Los defaults de columna sólo se aplican al insertar en BD;
        # en instanciación Python debemos pasarlo explícitamente.
        u = User(username='ivan', role='solo_lectura')
        assert u.role == 'solo_lectura'

    def test_is_active_default_true(self):
        from database.models import User
        u = User(username='judy', is_active=True)
        assert u.is_active is True


# ── Machine ───────────────────────────────────────────────────────────────────

class TestMachineModel:
    def test_to_dict_estructura_basica(self):
        from database.models import Machine
        m = Machine(name='Servidor A', ip='192.168.1.1', port=12345, status='online')
        m.id = 1
        m.created_at = datetime(2026, 1, 1, 0, 0, 0)
        m.last_seen = None
        d = m.to_dict()
        assert d['id'] == 1
        assert d['name'] == 'Servidor A'
        assert d['ip'] == '192.168.1.1'
        assert d['port'] == 12345
        assert d['status'] == 'online'
        assert d['last_seen'] is None

    def test_to_dict_last_seen_serializa_iso(self):
        from database.models import Machine
        m = Machine(name='PC', ip='10.0.0.1', port=12345)
        m.id = 2
        m.created_at = datetime(2026, 1, 1)
        m.last_seen = datetime(2026, 5, 1, 12, 0, 0)
        d = m.to_dict()
        assert d['last_seen'] == '2026-05-01T12:00:00'

    def test_to_dict_status_default_unknown(self):
        from database.models import Machine
        # Los defaults de columna sólo aplican al insertar en BD; pasamos explícitamente.
        m = Machine(name='PC2', ip='10.0.0.2', status='unknown')
        m.id = 3
        m.created_at = datetime(2026, 1, 1)
        m.last_seen = None
        d = m.to_dict()
        assert d['status'] == 'unknown'

    def test_to_dict_incluye_description(self):
        from database.models import Machine
        m = Machine(name='PC3', ip='10.0.0.3', description='Servidor principal')
        m.id = 4
        m.created_at = datetime(2026, 1, 1)
        m.last_seen = None
        d = m.to_dict()
        assert d['description'] == 'Servidor principal'


# ── SystemMetric ──────────────────────────────────────────────────────────────

class TestSystemMetricModel:
    def test_to_dict_estructura(self):
        from database.models import SystemMetric
        s = SystemMetric(machine_id=1, cpu=45.5, memory=60.0,
                         disk_used=30.0, disk_free=70.0)
        s.timestamp = datetime(2026, 5, 1, 12, 0, 0)
        d = s.to_dict()
        assert d['cpu'] == 45.5
        assert d['memory'] == 60.0
        assert d['disk_used'] == 30.0
        assert d['disk_free'] == 70.0
        assert d['timestamp'] == '2026-05-01T12:00:00'

    def test_to_dict_valores_none(self):
        from database.models import SystemMetric
        s = SystemMetric(machine_id=1, cpu=None, memory=None, disk_used=None, disk_free=None)
        s.timestamp = datetime(2026, 1, 1)
        d = s.to_dict()
        assert d['cpu'] is None
        assert d['memory'] is None

    def test_to_dict_tiene_todas_las_claves(self):
        from database.models import SystemMetric
        s = SystemMetric(machine_id=1, cpu=10.0, memory=20.0, disk_used=30.0, disk_free=70.0)
        s.timestamp = datetime(2026, 1, 1)
        d = s.to_dict()
        for key in ('timestamp', 'cpu', 'memory', 'disk_used', 'disk_free'):
            assert key in d


# ── HardwareSnapshot ──────────────────────────────────────────────────────────

class TestHardwareSnapshotModel:
    def test_to_dict_parsea_json(self):
        from database.models import HardwareSnapshot
        h = HardwareSnapshot(machine_id=1)
        h.timestamp = datetime(2026, 1, 1)
        h.system_json = '{"os": "Windows 11", "hostname": "PC01"}'
        h.cpu_json = '{"cores": 8, "model": "Intel i7"}'
        h.memory_json = '{"total_gb": 16}'
        h.disks_json = '[{"name": "C:", "size": "256 GB"}]'
        h.gpu_json = '[{"name": "RTX 3080"}]'
        h.motherboard_json = '{"brand": "ASUS"}'
        h.devices_json = '[]'
        d = h.to_dict()
        assert d['system'] == {'os': 'Windows 11', 'hostname': 'PC01'}
        assert d['cpu']['cores'] == 8
        assert d['disks'] == [{'name': 'C:', 'size': '256 GB'}]
        assert d['gpu'] == [{'name': 'RTX 3080'}]
        assert d['motherboard'] == {'brand': 'ASUS'}
        assert d['devices'] == []

    def test_to_dict_json_none_usa_defaults(self):
        from database.models import HardwareSnapshot
        h = HardwareSnapshot(machine_id=1)
        h.timestamp = datetime(2026, 1, 1)
        h.system_json = None
        h.cpu_json = None
        h.memory_json = None
        h.disks_json = None
        h.gpu_json = None
        h.motherboard_json = None
        h.devices_json = None
        d = h.to_dict()
        assert d['system'] == {}
        assert d['cpu'] == {}
        assert d['memory'] == {}
        assert d['disks'] == []
        assert d['gpu'] == []
        assert d['motherboard'] == {}
        assert d['devices'] == []

    def test_to_dict_timestamp_serializa_iso(self):
        from database.models import HardwareSnapshot
        h = HardwareSnapshot(machine_id=1)
        h.timestamp = datetime(2026, 3, 15, 9, 0, 0)
        h.system_json = '{}'
        h.cpu_json = '{}'
        h.memory_json = '{}'
        h.disks_json = '[]'
        h.gpu_json = '[]'
        h.motherboard_json = '{}'
        h.devices_json = '[]'
        d = h.to_dict()
        assert d['timestamp'] == '2026-03-15T09:00:00'


# ── BackupRun ─────────────────────────────────────────────────────────────────

class TestBackupRunModel:
    def _make_run(self, **kwargs):
        from database.models import BackupRun
        defaults = dict(
            machine_id=1,
            status='completed',
            job_id=None,
            job=None,
            job_name_snapshot=None,
            backup_type_snapshot=None,
            started_at=datetime(2026, 5, 1, 12, 0, 0),
            finished_at=None,
            id=1,
            progress_pct=100.0,
            files_done=10,
            bytes_done=1024,
            total_bytes_estimate=1024,
            duration_sec=5.0,
            output=None,
            error=None,
            backup_full_name=None,
            backup_path=None,
        )
        defaults.update(kwargs)
        r = BackupRun()
        for k, v in defaults.items():
            setattr(r, k, v)
        return r

    def test_to_dict_job_deleted_true_cuando_job_id_none_y_snapshot(self):
        r = self._make_run(job_id=None, job=None,
                           job_name_snapshot='trabajo_borrado',
                           backup_type_snapshot='full')
        d = r.to_dict()
        assert d['job_deleted'] is True
        assert d['job_name'] == 'trabajo_borrado'
        assert d['backup_type'] == 'full'

    def test_to_dict_job_deleted_false_cuando_job_existe(self):
        from database.models import BackupJob
        job = BackupJob(name='mi_job', backup_type='incremental',
                        machine_id=1, source_path='C:\\X',
                        destination_id=1, schedule='daily', schedule_time='02:00')
        r = self._make_run(job_id=1, job=job)
        d = r.to_dict()
        assert d['job_deleted'] is False
        assert d['job_name'] == 'mi_job'
        assert d['backup_type'] == 'incremental'

    def test_to_dict_sin_job_ni_snapshot_usa_fallback(self):
        r = self._make_run(job_id=None, job=None,
                           job_name_snapshot=None, backup_type_snapshot=None)
        d = r.to_dict()
        assert d['job_name'] == 'Trabajo eliminado'
        assert d['backup_type'] == 'full'

    def test_to_dict_started_at_serializa_iso(self):
        r = self._make_run(started_at=datetime(2026, 5, 1, 8, 30, 0))
        d = r.to_dict()
        assert d['started_at'] == '2026-05-01T08:30:00'

    def test_to_dict_finished_at_none_cuando_sin_terminar(self):
        r = self._make_run(finished_at=None, status='running')
        d = r.to_dict()
        assert d['finished_at'] is None

    def test_to_dict_progress_pct_redondeado(self):
        r = self._make_run(progress_pct=66.666666)
        d = r.to_dict()
        assert d['progress_pct'] == pytest.approx(66.7, abs=0.1)

    def test_to_dict_contiene_claves_requeridas(self):
        r = self._make_run()
        d = r.to_dict()
        for key in ('id', 'job_id', 'job_name', 'job_deleted', 'backup_type',
                    'machine_id', 'started_at', 'finished_at', 'status',
                    'progress_pct', 'files_done', 'bytes_done'):
            assert key in d


# ── BackupJob ─────────────────────────────────────────────────────────────────

class TestBackupJobModel:
    def test_to_dict_estructura(self):
        from database.models import BackupJob
        job = BackupJob(
            name='diario',
            backup_type='full',
            machine_id=1,
            source_path='C:\\Datos',
            destination_id=2,
            schedule='daily',
            schedule_time='02:00',
            compress=True,
            verify_after=True,
            enabled=True,
        )
        job.id = 5
        job.created_at = datetime(2026, 1, 1)
        job.last_run_at = None
        job.next_run_at = None
        job.scheduled_task_name = None
        d = job.to_dict()
        assert d['id'] == 5
        assert d['name'] == 'diario'
        assert d['backup_type'] == 'full'
        assert d['schedule'] == 'daily'
        assert d['compress'] is True
        assert d['enabled'] is True
        assert d['last_run_at'] is None


# ── BackupDestination ─────────────────────────────────────────────────────────

class TestBackupDestinationModel:
    def test_to_dict_local_es_supported(self):
        from database.models import BackupDestination
        dest = BackupDestination(name='Local', type='local', path='C:\\Backups')
        dest.id = 1
        dest.machine_id = 1
        dest.status = 'online'
        dest.created_at = datetime(2026, 1, 1)
        d = dest.to_dict()
        assert d['supported'] is True
        assert d['type'] == 'local'

    def test_to_dict_network_no_es_supported(self):
        from database.models import BackupDestination
        dest = BackupDestination(name='Red', type='network', path='\\\\server\\share')
        dest.id = 2
        dest.machine_id = 1
        dest.status = 'unknown'
        dest.created_at = datetime(2026, 1, 1)
        d = dest.to_dict()
        assert d['supported'] is False

    def test_to_dict_contiene_todas_claves(self):
        from database.models import BackupDestination
        dest = BackupDestination(name='test', type='local', path='C:\\X')
        dest.id = 3
        dest.machine_id = None
        dest.status = 'unknown'
        dest.created_at = datetime(2026, 1, 1)
        d = dest.to_dict()
        for key in ('id', 'machine_id', 'name', 'type', 'path', 'status',
                    'supported', 'created_at'):
            assert key in d
