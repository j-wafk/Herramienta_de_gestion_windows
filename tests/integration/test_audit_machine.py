# tests/integration/test_audit_machine.py
"""Tests para que log_action registre la máquina correcta."""
import os

os.environ.setdefault('SECRET_KEY', 'test_secret')
os.environ.setdefault('ADMIN_PASSWORD', 'Admin12345678!')
os.environ.setdefault('FIELD_ENCRYPTION_KEY', 'test_field_encryption_key_32bytes!!')
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

import logging
import pytest


@pytest.fixture(scope='module')
def app():
    from main import create_app
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def captured_audit():
    """Captura las líneas escritas al logger 'audit'."""
    captured = []

    class _H(logging.Handler):
        def emit(self, record):
            captured.append(record.getMessage())

    log = logging.getLogger('audit')
    h = _H()
    log.addHandler(h)
    yield captured
    log.removeHandler(h)


def test_log_action_machine_id_explicito(app, captured_audit):
    """machine_id explícito → la etiqueta debe ser el nombre de la máquina."""
    from utils.audit import log_action
    from database.models import Machine
    with app.app_context():
        m = Machine.query.first()
        log_action('test_action', 'res1', machine_id=m.id)
    assert any(f'machine={m.name.replace(" ", "_")}' in line for line in captured_audit), \
        f'Esperaba machine={m.name} en {captured_audit}'


def test_log_action_machine_id_inexistente(app, captured_audit):
    """machine_id no encontrado → debe quedar como id:<n> (no 'local')."""
    from utils.audit import log_action
    with app.app_context():
        log_action('test_action', 'res2', machine_id=9999)
    assert any('machine=id:9999' in line for line in captured_audit), captured_audit


def test_log_action_sin_request_y_sin_machine_id(app, captured_audit):
    """Sin request context y sin machine_id explícito → 'local'."""
    from utils.audit import log_action
    with app.app_context():
        log_action('test_action', 'res3')
    assert any('machine=local' in line for line in captured_audit), captured_audit


def test_log_action_machine_id_anula_request(app, captured_audit):
    """Si llega un request con un machine_id, el explícito debe ganar."""
    from utils.audit import log_action
    from database.models import Machine
    with app.app_context():
        m = Machine.query.first()
        client = app.test_client()
        # Simulamos el request: enviamos machine_id=9999 pero log_action recibe el real.
        with app.test_request_context('/?machine_id=9999'):
            log_action('test_action', 'res4', machine_id=m.id)
    assert any(f'machine={m.name.replace(" ", "_")}' in line for line in captured_audit), \
        f'El explícito debe prevalecer. Líneas: {captured_audit}'
