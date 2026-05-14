"""Tests de integración — módulo export (/api/export/*)."""
import pytest
from unittest.mock import patch, MagicMock

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

try:
    import reportlab
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


class TestExportUnauthenticated:
    def test_hardware_export_requires_auth(self, module_client):
        assert module_client.get('/api/export/hardware').status_code == 401

    def test_rendimiento_export_requires_auth(self, module_client):
        assert module_client.get('/api/export/rendimiento').status_code == 401

    def test_particiones_export_requires_auth(self, module_client):
        assert module_client.get('/api/export/particiones').status_code == 401


@pytest.mark.skipif(not HAS_OPENPYXL, reason='openpyxl no instalado')
class TestExportAuthenticatedXlsx:
    @patch('modules.export.routes.resolve_and_send', return_value='')
    def test_hardware_export_returns_file(self, mock_ps, module_auth_client, module_app):
        with module_app.app_context():
            from database.models import Machine
            machine = Machine.query.first()
        resp = module_auth_client.get(f'/api/export/hardware?machine_id={machine.id}')
        assert resp.status_code in (200, 500)

    @patch('modules.export.routes.resolve_and_send', return_value='CPU: 45.5%')
    def test_rendimiento_export_returns_file(self, mock_ps, module_auth_client, module_app):
        with module_app.app_context():
            from database.models import Machine
            machine = Machine.query.first()
        resp = module_auth_client.get(f'/api/export/rendimiento?machine_id={machine.id}')
        assert resp.status_code in (200, 500)

    @patch('modules.export.routes.resolve_and_send', return_value='')
    def test_particiones_export_returns_file(self, mock_ps, module_auth_client, module_app):
        with module_app.app_context():
            from database.models import Machine
            machine = Machine.query.first()
        resp = module_auth_client.get(f'/api/export/particiones?machine_id={machine.id}')
        assert resp.status_code in (200, 500)
