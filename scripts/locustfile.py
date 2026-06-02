"""
Pruebas de carga básicas con Locust.

Uso:
    pip install locust==2.20.0
    locust -f scripts/locustfile.py --host https://localhost

Modo headless (CLI):
    locust -f scripts/locustfile.py --host https://localhost --headless -u 20 -r 2 -t 60s

Abrir UI:  http://localhost:8089

Configuración recomendada para una prueba inicial:
    Number of users: 20
    Spawn rate:      2 users/second
    Run time:        2 minutos

Variables de entorno opcionales:
    LOCUST_USER       (default: admin)
    LOCUST_PASSWORD   (default: admin123)

Nota: el rate-limit del endpoint /auth/login (5/min por IP) impide que cada
usuario virtual haga login independientemente. Por eso hacemos un único login
en test_start y compartimos la cookie de sesión entre todos los usuarios — esto
también es realista: simula a un administrador ya autenticado generando tráfico.
"""

import os
import re
import requests
import urllib3
from locust import HttpUser, task, between, events

# El despliegue Docker usa certificado autofirmado en nginx — silenciamos warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

USERNAME = os.environ.get('LOCUST_USER', 'admin')
PASSWORD = os.environ.get('LOCUST_PASSWORD', 'admin123')

CSRF_RE = re.compile(r'name="csrf_token"\s+value="([^"]+)"')

# Cookies de sesión compartidas entre todos los usuarios virtuales (un solo login).
SHARED_COOKIES = {}


def login_inicial(host):
    """Hace un login real y devuelve las cookies de sesión."""
    s = requests.Session()
    s.verify = False
    r = s.get(f'{host}/auth/login', timeout=10)
    r.raise_for_status()
    match = CSRF_RE.search(r.text)
    if not match:
        raise RuntimeError('No se encontró csrf_token en el HTML de login')
    csrf_token = match.group(1)
    r2 = s.post(
        f'{host}/auth/login',
        data={'username': USERNAME, 'password': PASSWORD, 'csrf_token': csrf_token},
        headers={'Referer': f'{host}/auth/login'},
        allow_redirects=False,
        timeout=10,
    )
    if r2.status_code != 302:
        raise RuntimeError(f'Login inicial falló (status={r2.status_code})')
    return s.cookies.get_dict()


class UsuarioGeneral(HttpUser):
    """Operador/lector — consulta el sistema periódicamente. 80% del tráfico."""

    weight = 4
    wait_time = between(1, 3)

    def on_start(self):
        self.client.verify = False
        for k, v in SHARED_COOKIES.items():
            self.client.cookies.set(k, v)

    @task(3)
    def ver_maquinas(self):
        self.client.get('/api/machines', name='/api/machines')

    @task(3)
    def ver_metricas(self):
        self.client.get('/api/rendimiento/system', name='/api/rendimiento/system')

    @task(2)
    def ver_hardware_snapshot(self):
        self.client.get('/api/hardware/snapshot', name='/api/hardware/snapshot')

    @task(2)
    def ver_monitorizacion(self):
        self.client.get('/api/monitorizacion/summary', name='/api/monitorizacion/summary')

    @task(2)
    def ver_historial_backup(self):
        self.client.get('/api/backup/history?limit=10', name='/api/backup/history')

    @task(1)
    def health_check(self):
        self.client.get('/health', name='/health')


class UsuarioAdmin(HttpUser):
    """Administrador — operaciones puntuales además de monitorización. 20% del tráfico."""

    weight = 1
    wait_time = between(3, 6)

    def on_start(self):
        self.client.verify = False
        for k, v in SHARED_COOKIES.items():
            self.client.cookies.set(k, v)

    @task(2)
    def ver_maquinas(self):
        self.client.get('/api/machines', name='/api/machines')

    @task(1)
    def ver_audit_log(self):
        self.client.get('/auth/api/registros?limit=20', name='/auth/api/registros')

    @task(1)
    def ver_backup_jobs(self):
        self.client.get('/api/backup/jobs', name='/api/backup/jobs')

    @task(1)
    def ping_maquinas(self):
        self.client.post('/api/machines/ping_all', name='/api/machines/ping_all')

    @task(1)
    def exportar_rendimiento(self):
        self.client.get(
            '/api/export/rendimiento?format=xlsx&days=1',
            name='/api/export/rendimiento',
        )


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print(f'[locust] Usuario de login: {USERNAME}')
    print(f'[locust] Host objetivo:    {environment.host}')
    try:
        cookies = login_inicial(environment.host)
        SHARED_COOKIES.update(cookies)
        print(f'[locust] Login OK — sesión compartida lista ({len(cookies)} cookie(s))')
    except Exception as exc:
        print(f'[locust] ERROR en login inicial: {exc}')
        environment.runner.quit()


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    stats = environment.stats.total
    print('\n[locust] Resumen:')
    print(f'  Peticiones totales: {stats.num_requests}')
    print(f'  Fallos:             {stats.num_failures}')
    print(f'  Latencia media:     {stats.avg_response_time:.0f} ms')
    print(f'  Latencia p95:       {stats.get_response_time_percentile(0.95):.0f} ms')
