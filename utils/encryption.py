# utils/encryption.py
"""Column-level encryption at rest using Fernet (AES-128-CBC + HMAC-SHA256).

Key management:
  - FIELD_ENCRYPTION_KEY env var (required, 32+ hex chars).
  - A SHA-256 of that key is used as the Fernet key (32 bytes → base64url).
  - A separate SHA-256 of 'hmac:<key>' is used for HMAC hashes.

All instances are lazy-initialised on first DB access so that the env var
only needs to exist by the time SQLAlchemy processes a value (not at import
time).

Legacy plaintext fallback: if decryption fails for an existing row the raw
value is returned unchanged.  The _migrate_encryption_columns() function in
main.py re-encrypts any such rows on startup.
"""
import base64
import hashlib
import hmac as _hmac
import os

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

_fernet_instance = None
_hmac_key_cache = None


def _raw_key() -> bytes:
    key_str = os.environ.get('FIELD_ENCRYPTION_KEY', '').strip()
    if not key_str:
        raise RuntimeError(
            "La variable de entorno 'FIELD_ENCRYPTION_KEY' es obligatoria. "
            "Genera una con: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    return key_str.encode('utf-8')


def _get_fernet() -> Fernet:
    global _fernet_instance
    if _fernet_instance is None:
        derived = hashlib.sha256(_raw_key()).digest()
        _fernet_instance = Fernet(base64.urlsafe_b64encode(derived))
    return _fernet_instance


def _get_hmac_key() -> bytes:
    global _hmac_key_cache
    if _hmac_key_cache is None:
        _hmac_key_cache = hashlib.sha256(b'hmac:' + _raw_key()).digest()
    return _hmac_key_cache


def compute_search_hash(value: str) -> str:
    """Return HMAC-SHA256 hex of the lowercased, stripped value.

    Used for searchable unique fields (e.g. User.email_hash) where the
    encrypted column cannot be queried directly.  Returns None if value is
    empty/None.
    """
    if not value:
        return None
    normalized = value.strip().lower()
    return _hmac.new(_get_hmac_key(), normalized.encode('utf-8'), hashlib.sha256).hexdigest()


# Fernet tokens always start with this prefix after base64url encoding.
_FERNET_PREFIX = 'gAAAAA'


class _EncryptedMixin:
    """Shared encrypt/decrypt logic for SQLAlchemy TypeDecorators."""
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Encrypt Python value → DB bytes (stored as ASCII text)."""
        if value is None:
            return None
        return _get_fernet().encrypt(value.encode('utf-8')).decode('ascii')

    def process_result_value(self, value, dialect):
        """Decrypt DB bytes → Python value."""
        if value is None:
            return None
        if not value.startswith(_FERNET_PREFIX):
            # Legacy plaintext row — return as-is; will be re-encrypted on
            # the next write or by _migrate_encryption_columns().
            return value
        try:
            return _get_fernet().decrypt(value.encode('ascii')).decode('utf-8')
        except InvalidToken:
            # Wrong key or corrupted data — return raw to avoid data loss.
            return value


class EncryptedString(_EncryptedMixin, TypeDecorator):
    """Fernet-encrypted column backed by TEXT (for short strings ≤ ~500 chars)."""
    impl = Text


class EncryptedText(_EncryptedMixin, TypeDecorator):
    """Fernet-encrypted column backed by TEXT (for long bodies / HTML)."""
    impl = Text
