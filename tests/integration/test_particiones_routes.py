"""Tests de integración — módulo particiones (/api/particiones/*)."""
from unittest.mock import patch
import pytest

_PS_PATH = 'modules.particiones.routes.resolve_and_send'

DISKS_OUTPUT = (
    'DiskNumber: 0\nModel: Samsung SSD\nSize: 256 GB\n'
    'Interface: SATA\nStatus: Online\nPartitionStyle: GPT\n'
    'Temperature: 35\nPowerOnHours: 1500\nSmartStatus: OK\n'
    'FreeSpace: 100 GB\n---\n'
)
PARTITIONS_OUTPUT = (
    'DiskId: disk0\nPartNumber: 1\nLetter: C\nLabel: Sistema\n'
    'Size: 100 GB\nFilesystem: NTFS\nType: system\n---\n'
)


@pytest.fixture(scope='module')
def machine_id(module_app):
    with module_app.app_context():
        from database.models import Machine
        return Machine.query.first().id


# ─── Unauthenticated ───────────────────────────────────────────────────────────

class TestParticionesUnauthenticated:
    def test_disks_requires_auth(self, module_client):
        assert module_client.get('/api/particiones/disks').status_code == 401

    def test_partitions_requires_auth(self, module_client):
        assert module_client.get('/api/particiones/partitions').status_code == 401

    def test_disk_detail_requires_auth(self, module_client):
        assert module_client.get('/api/particiones/disk_detail').status_code == 401

    def test_operation_requires_auth(self, module_client):
        assert module_client.post('/api/particiones/partition_operation', json={}).status_code == 401


# ─── Listado de discos y particiones ───────────────────────────────────────────

class TestListDisks:
    @patch(_PS_PATH, return_value=DISKS_OUTPUT)
    def test_disks_returns_200(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/particiones/disks?machine_id={machine_id}')
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value='Error al obtener')
    def test_disks_error_returns_500(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/particiones/disks?machine_id={machine_id}')
        assert resp.status_code == 500

    @patch(_PS_PATH, return_value='')
    def test_disks_empty_returns_500(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/particiones/disks?machine_id={machine_id}')
        assert resp.status_code == 500


class TestListPartitions:
    @patch(_PS_PATH, return_value=PARTITIONS_OUTPUT)
    def test_partitions_returns_200(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/particiones/partitions?machine_id={machine_id}')
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value=PARTITIONS_OUTPUT)
    def test_partitions_with_disk_id_filter(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(
            f'/api/particiones/partitions?machine_id={machine_id}&disk_id=disk0'
        )
        assert resp.status_code == 200

    def test_partitions_invalid_disk_id_returns_400(self, module_auth_client):
        resp = module_auth_client.get('/api/particiones/partitions?disk_id=invalid!!')
        assert resp.status_code == 400

    @patch(_PS_PATH, return_value='Error al obtener')
    def test_partitions_error_returns_500(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(f'/api/particiones/partitions?machine_id={machine_id}')
        assert resp.status_code == 500


# ─── Disk detail ───────────────────────────────────────────────────────────────

class TestDiskDetail:
    def test_missing_disk_id_returns_400(self, module_auth_client):
        resp = module_auth_client.get('/api/particiones/disk_detail')
        assert resp.status_code == 400

    def test_invalid_disk_id_returns_400(self, module_auth_client):
        resp = module_auth_client.get('/api/particiones/disk_detail?disk_id=foo')
        assert resp.status_code == 400

    @patch(_PS_PATH, return_value='DiskNumber: 0\nModel: Samsung')
    def test_valid_disk_id_returns_200(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.get(
            f'/api/particiones/disk_detail?disk_id=disk0&machine_id={machine_id}'
        )
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value='Error')
    def test_error_returns_500(self, mock_ps, module_auth_client):
        resp = module_auth_client.get('/api/particiones/disk_detail?disk_id=disk0')
        assert resp.status_code == 500


# ─── Operaciones ───────────────────────────────────────────────────────────────

class TestPartitionOperations:
    def test_no_data_returns_400(self, module_auth_client):
        # request.json on empty POST is None
        resp = module_auth_client.post('/api/particiones/partition_operation',
                                       json={})
        assert resp.status_code == 400

    def test_missing_operation_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/particiones/partition_operation',
                                       json={'disk_id': 'disk0'})
        assert resp.status_code == 400

    def test_invalid_operation_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/particiones/partition_operation',
                                       json={'operation': 'invalid_op'})
        assert resp.status_code == 400

    @patch(_PS_PATH, return_value='Partición creada')
    def test_create_partition_success(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/particiones/partition_operation', json={
            'operation': 'create',
            'disk_id': 'disk1',
            'size': 50,
            'filesystem': 'NTFS',
            'label': 'NuevaPart',
            'machine_id': machine_id,
        })
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value='Partición creada')
    def test_create_partition_with_letter(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/particiones/partition_operation', json={
            'operation': 'create',
            'disk_id': 'disk1',
            'size': 50,
            'filesystem': 'NTFS',
            'letter': 'E',
            'machine_id': machine_id,
        })
        assert resp.status_code == 200

    def test_create_invalid_size_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/particiones/partition_operation', json={
            'operation': 'create',
            'disk_id': 'disk1',
            'size': 'invalid',
            'filesystem': 'NTFS',
        })
        assert resp.status_code == 400

    def test_create_invalid_filesystem_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/particiones/partition_operation', json={
            'operation': 'create',
            'disk_id': 'disk1',
            'size': 50,
            'filesystem': 'BAD_FS',
        })
        assert resp.status_code == 400

    def test_create_invalid_letter_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/particiones/partition_operation', json={
            'operation': 'create',
            'disk_id': 'disk1',
            'size': 50,
            'filesystem': 'NTFS',
            'letter': 'C',  # C is reserved
        })
        assert resp.status_code == 400

    @patch(_PS_PATH, return_value='Partición formateada')
    def test_format_partition_success(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/particiones/partition_operation', json={
            'operation': 'format',
            'partition_id': '1',
            'filesystem': 'NTFS',
            'label': 'MyVol',
            'machine_id': machine_id,
        })
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value='Partición formateada')
    def test_format_partition_no_label(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/particiones/partition_operation', json={
            'operation': 'format',
            'partition_id': '1',
            'filesystem': 'FAT32',
            'machine_id': machine_id,
        })
        assert resp.status_code == 200

    def test_format_invalid_partition_id_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/particiones/partition_operation', json={
            'operation': 'format',
            'partition_id': 'invalid!',
            'filesystem': 'NTFS',
        })
        assert resp.status_code == 400

    @patch(_PS_PATH, return_value='Partición eliminada')
    def test_delete_partition_success(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/particiones/partition_operation', json={
            'operation': 'delete',
            'partition_id': '1',
            'machine_id': machine_id,
        })
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value='Partición redimensionada')
    def test_resize_partition_success(self, mock_ps, module_auth_client, machine_id):
        resp = module_auth_client.post('/api/particiones/partition_operation', json={
            'operation': 'resize',
            'partition_id': '1',
            'new_size': 80,
            'machine_id': machine_id,
        })
        assert resp.status_code == 200

    def test_resize_invalid_size_returns_400(self, module_auth_client):
        resp = module_auth_client.post('/api/particiones/partition_operation', json={
            'operation': 'resize',
            'partition_id': '1',
            'new_size': 'invalid',
        })
        assert resp.status_code == 400
