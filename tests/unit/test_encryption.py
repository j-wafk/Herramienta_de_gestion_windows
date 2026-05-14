# tests/unit/test_encryption.py
"""Tests unitarios para utils/encryption.py"""
import os
import pytest

os.environ.setdefault('FIELD_ENCRYPTION_KEY', 'test_field_encryption_key_32bytes!!')

import utils.encryption as enc_module


@pytest.fixture(autouse=True)
def reset_singletons():
    """Resetea los singletons Fernet / HMAC antes y después de cada test."""
    enc_module._fernet_instance = None
    enc_module._hmac_key_cache = None
    yield
    enc_module._fernet_instance = None
    enc_module._hmac_key_cache = None


# ── compute_search_hash ───────────────────────────────────────────────────────

class TestComputeSearchHash:
    def test_none_devuelve_none(self):
        from utils.encryption import compute_search_hash
        assert compute_search_hash(None) is None

    def test_vacio_devuelve_none(self):
        from utils.encryption import compute_search_hash
        assert compute_search_hash('') is None

    def test_hash_es_hex_de_64_chars(self):
        from utils.encryption import compute_search_hash
        h = compute_search_hash('test@example.com')
        assert len(h) == 64
        assert all(c in '0123456789abcdef' for c in h)

    def test_normaliza_mayusculas(self):
        from utils.encryption import compute_search_hash
        assert compute_search_hash('Test@Example.COM') == compute_search_hash('test@example.com')

    def test_normaliza_espacios_iniciales_y_finales(self):
        from utils.encryption import compute_search_hash
        assert compute_search_hash('  user@test.com  ') == compute_search_hash('user@test.com')

    def test_distintos_valores_distintos_hashes(self):
        from utils.encryption import compute_search_hash
        assert compute_search_hash('user1@test.com') != compute_search_hash('user2@test.com')

    def test_determinista(self):
        from utils.encryption import compute_search_hash
        v = 'deterministic@test.com'
        assert compute_search_hash(v) == compute_search_hash(v)

    def test_sin_clave_lanza_error(self, monkeypatch):
        from utils.encryption import compute_search_hash
        monkeypatch.delenv('FIELD_ENCRYPTION_KEY', raising=False)
        with pytest.raises(RuntimeError, match='FIELD_ENCRYPTION_KEY'):
            compute_search_hash('any@value.com')


# ── _EncryptedMixin (vía EncryptedString) ────────────────────────────────────

class TestEncryptedMixin:
    def test_cifra_y_descifra_correctamente(self):
        from utils.encryption import EncryptedString
        col = EncryptedString()
        original = 'valor secreto'
        encrypted = col.process_bind_param(original, None)
        assert encrypted != original
        assert encrypted.startswith('gAAAAA')
        assert col.process_result_value(encrypted, None) == original

    def test_bind_none_permanece_none(self):
        from utils.encryption import EncryptedString
        assert EncryptedString().process_bind_param(None, None) is None

    def test_result_none_permanece_none(self):
        from utils.encryption import EncryptedString
        assert EncryptedString().process_result_value(None, None) is None

    def test_texto_plano_legacy_se_devuelve_tal_cual(self):
        """Un valor sin prefijo Fernet se devuelve sin descifrar (compatibilidad)."""
        from utils.encryption import EncryptedString
        plain = 'texto_plano_sin_cifrar'
        result = EncryptedString().process_result_value(plain, None)
        assert result == plain

    def test_token_corrupto_devuelve_valor_raw(self):
        """Token con prefijo Fernet pero corrupto → devuelve el valor tal cual."""
        from utils.encryption import EncryptedString
        corrupted = 'gAAAAA' + 'X' * 50
        result = EncryptedString().process_result_value(corrupted, None)
        assert result == corrupted

    def test_string_corto_y_largo_roundtrip(self):
        from utils.encryption import EncryptedString
        col = EncryptedString()
        for value in ['a', 'x' * 500]:
            enc = col.process_bind_param(value, None)
            assert col.process_result_value(enc, None) == value

    def test_caracteres_unicode(self):
        from utils.encryption import EncryptedString
        col = EncryptedString()
        value = 'José García <jose@empresa.es>'
        enc = col.process_bind_param(value, None)
        assert col.process_result_value(enc, None) == value


class TestEncryptedText:
    def test_texto_largo_roundtrip(self):
        from utils.encryption import EncryptedText
        col = EncryptedText()
        html = '<html><body>' + 'contenido ' * 500 + '</body></html>'
        enc = col.process_bind_param(html, None)
        assert enc.startswith('gAAAAA')
        assert col.process_result_value(enc, None) == html

    def test_none_permanece_none(self):
        from utils.encryption import EncryptedText
        col = EncryptedText()
        assert col.process_bind_param(None, None) is None
        assert col.process_result_value(None, None) is None
