"""Tests de integración — módulo particiones (/api/particiones/*)."""
from unittest.mock import patch

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


class TestParticionesUnauthenticated:
    def test_disks_requires_auth(self, module_client):
        assert module_client.get('/api/particiones/disks').status_code == 401

    def test_partitions_requires_auth(self, module_client):
        assert module_client.get('/api/particiones/partitions').status_code == 401

    def test_operation_requires_auth(self, module_client):
        assert module_client.post('/api/particiones/partition_operation', json={}).status_code == 401


class TestParticionesAuthenticated:
    @patch(_PS_PATH, return_value=DISKS_OUTPUT)
    def test_list_disks_returns_200(self, mock_ps, module_auth_client, module_app):
        with module_app.app_context():
            from database.models import Machine
            machine = Machine.query.first()
        resp = module_auth_client.get(f'/api/particiones/disks?machine_id={machine.id}')
        assert resp.status_code == 200

    @patch(_PS_PATH, return_value=PARTITIONS_OUTPUT)
    def test_list_partitions_returns_200(self, mock_ps, module_auth_client, module_app):
        with module_app.app_context():
            from database.models import Machine
            machine = Machine.query.first()
        resp = module_auth_client.get(f'/api/particiones/partitions?machine_id={machine.id}')
        assert resp.status_code == 200

    def test_partition_operation_missing_fields(self, module_auth_client):
        resp = module_auth_client.post('/api/particiones/partition_operation', json={})
        assert resp.status_code in (400, 422)

    def test_partition_operation_invalid_type(self, module_auth_client):
        resp = module_auth_client.post('/api/particiones/partition_operation', json={
            'operation': 'invalid_op',
        })
        assert resp.status_code in (400, 422)
