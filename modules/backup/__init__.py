# modules/backup/__init__.py
"""
Módulo de gestión de copias de seguridad
Incluye backup, restauración, compresión y programación
"""

from .routes import backup_bp

__all__ = ['backup_bp']