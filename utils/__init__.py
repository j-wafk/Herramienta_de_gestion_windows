# utils/__init__.py
"""
Utilidades compartidas para la aplicación Flask
Incluye gestión de caché, cliente PowerShell y tareas en segundo plano
"""

from .cache_manager import CacheManager
from .powershell_client import send_command_to_powershell, health_check_powershell
from .background_tasks import background_data_refresh

__all__ = [
    'CacheManager',
    'send_command_to_powershell', 
    'health_check_powershell',
    'background_data_refresh'
]