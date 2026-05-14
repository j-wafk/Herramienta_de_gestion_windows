# extensions.py
# Instancias de extensiones Flask desacopladas de la app para evitar imports circulares.
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

# Rate limiter — almacenamiento en memoria del proceso (sin storage_uri).
#
# Limitación conocida: los contadores se pierden al reiniciar el contenedor.
# Un atacante con capacidad de provocar reinicios podría resetear el límite.
# Para producción real con varias instancias o reinicios frecuentes, configurar
# un backend persistente:
#
#     limiter = Limiter(
#         key_func=get_remote_address,
#         storage_uri="redis://redis:6379/0",
#         default_limits=[],
#     )
#
# La IP de origen viene de get_remote_address(), que lee request.remote_addr.
# ProxyFix (configurado en main.py) hace que esa IP sea la real del cliente
# tras nginx, no la IP interna del contenedor del proxy inverso.
limiter = Limiter(key_func=get_remote_address, default_limits=[])
csrf = CSRFProtect()
