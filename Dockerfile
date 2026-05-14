FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema necesarias para psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

# IMPORTANTE: workers=1 es OBLIGATORIO.
#  - El CacheManager y el histórico de métricas viven en memoria del proceso.
#  - El hilo de background (background_data_refresh) y los pollers se inician
#    una sola vez por proceso.
#  - Con workers=2+ cada worker tendría su propia caché y dispararía pollers
#    duplicados → métricas inconsistentes en el dashboard y notificaciones por
#    duplicado. Para escalar horizontalmente: mover CacheManager a Redis y
#    convertir los pollers en un servicio independiente.
# Threads=4 cubre la concurrencia de peticiones HTTP normales y la del thread
# de background sin necesidad de procesos adicionales.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--timeout", "120", "main:create_app()"]
