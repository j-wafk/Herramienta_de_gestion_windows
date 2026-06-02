# modules/rendimiento/__init__.py
"""
Módulo de monitoreo de rendimiento del sistema
Incluye CPU, memoria, procesos, red y servicios
"""

from .routes import rendimiento_bp

__all__ = ['rendimiento_bp']
