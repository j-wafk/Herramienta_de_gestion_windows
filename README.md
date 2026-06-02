# Herramienta de Gestión Remota para Windows

![Tests](https://github.com/j-wafk/Herramienta_de_gestion_windows/actions/workflows/tests.yml/badge.svg)

Sistema de administración y monitorización remota para entornos Windows. Expone una interfaz web completa para supervisar rendimiento, gestionar discos, ejecutar backups y controlar servicios, todo ello con autenticación por roles, cifrado de datos sensibles, base de datos PostgreSQL y despliegue Docker.

## Arquitectura

```
Navegador Web
     │ HTTPS (nginx)
     ▼
Servidor Flask (Python)
     │ TCP / TLS opcional
     ▼
Servidor PowerShell (Windows)
     │ WMI / diskpart / PowerShell
     ▼
Sistema Windows objetivo
```

El servidor PowerShell se ejecuta con privilegios de Administrador y acepta comandos del backend Flask a través de un socket TCP (con soporte TLS opcional). Flask actúa como API REST y servidor de plantillas HTML.

## Características

### Monitorización de Rendimiento
- CPU, memoria y disco en tiempo real con gráficos Chart.js
- Histórico de 15 puntos, refresco automático cada 5 segundos
- Lista de procesos con CPU %, memoria y PID
- Caché en memoria con TTL configurable (3 s por defecto), thread-safe

### Gestión de Discos y Particiones
- Inventario de discos físicos (modelo, interfaz, temperatura, horas)
- Crear, formatear (NTFS / FAT32 / exFAT / ReFS), eliminar y redimensionar particiones
- Letras de unidad válidas: D–Z (A, B y C están reservadas)

### Copias de Seguridad
- Tipos: Completo, Incremental, Diferencial
- Compresión ZIP (4 niveles), restauración, verificación de integridad
- El flag `encrypt` del trabajo está reservado para versiones futuras (sin efecto en v1.0); `notify` está implementado y activo
- Trabajos de backup configurables con destinos locales (tipo `network`, `cloud` y `ftp` reservados para versiones futuras)
- Programación mediante Windows Task Scheduler (diario / semanal / mensual)
- Historial de ejecuciones con progreso en tiempo real y preservación tras eliminación del trabajo

### Monitorización de Servicios
- Poller en background para endpoints TCP, UDP y HTTPS con icono por tipo de servicio (WinRM, IIS, SQL, RDP, DNS, API…)
- Registro histórico de cambios de estado con timestamps y latencia
- Notificaciones por email cuando un servicio cae o se recupera

### Gestión Multi-Máquina
- Registro de máquinas remotas (IP:puerto, descripción)
- Estado online / offline / warning con timestamps de última conexión
- Dashboard centralizado con selector de máquina activa en la cabecera
- Estadísticas agregadas en la vista general

### Hardware e Inventario
- CPU, memoria, GPU, placa base, dispositivos conectados
- Snapshots JSON almacenados por máquina en PostgreSQL (un registro por máquina, actualización automática)

### Red
- Interfaces de red, configuración TCP/IP y DNS
- Herramientas de diagnóstico: ping, traceroute, ipconfig, netstat, release/renew, flush DNS

### Autenticación y Control de Acceso
- Login con rate limiting (5 req/min, 20 req/hora)
- Bloqueo automático de cuenta tras 5 intentos fallidos (15 minutos)
- Bloqueo adicional de 10 minutos cuando se dispara el rate-limit (no sorteable cambiando de IP)
- Protección contra enumeración de usuarios mediante verificación en tiempo constante
- Sesión permanente de 8 horas con cierre automático por inactividad (30 min)
- Cuatro roles: `superadmin`, `admin`, `operador`, `solo_lectura`
- Perfiles de usuario: nombre completo, email cifrado, idioma, tema, color de avatar, preferencias de notificación
- Auditoría completa de acciones administrativas con log en `logs/audit.log`

### Notificaciones por Email
- Cola persistente en base de datos con reintentos y backoff exponencial
- Plantillas HTML para: bienvenida, cambio de contraseña, backup completado/fallido, máquina offline, servicio caído, prueba
- Preferencias por usuario: machine_offline, service_down, backup_failed, backup_completed, daily_summary
- Compatible con Gmail/Outlook (STARTTLS), SMTPS y MailHog en desarrollo

### Cifrado en Reposo
- Campos sensibles (email, nombre completo, cuerpo de correos) cifrados con Fernet (AES-128-CBC + HMAC-SHA256)
- Hash HMAC-SHA256 del email para búsquedas sin descifrar
- Migración automática al arrancar: cifra filas en texto plano existentes

### Interfaz y Usabilidad
- Tema claro / oscuro persistente por usuario
- Internacionalización ES / EN con `data-i18n` en el DOM
- Modal de preferencias de usuario accesible desde la cabecera

### Exportación
- Reportes en PDF y Excel de hardware, rendimiento, particiones y red

## Tecnologías

| Capa | Tecnologías |
|------|------------|
| Backend | Python 3.8+, Flask 2.3, SQLAlchemy, Flask-Migrate, Gunicorn |
| Seguridad | Flask-Talisman (CSP/HSTS), Flask-WTF (CSRF), Flask-Limiter, Flask-Login, cryptography (Fernet) |
| Base de datos | PostgreSQL 12+ con SSL |
| Frontend | HTML5, CSS3 (Grid/Flexbox), JavaScript ES6, Chart.js |
| Email | SMTP con cola persistente en BD y backoff exponencial |
| Exportación | openpyxl (Excel), ReportLab (PDF) |
| Windows | PowerShell 5.1+, WMI, diskpart, Task Scheduler |
| Infraestructura | Docker, Docker Compose, nginx (TLS 1.2+) |
| Testing | pytest, pytest-cov, pytest-flask, pytest-mock |

## Estructura del Proyecto

```
Herramienta-de-gestion/
├── main.py                        # Punto de entrada Flask + migraciones idempotentes
├── config.py                      # Configuración centralizada (.env)
├── extensions.py                  # Flask extensions (Limiter, CSRF)
├── compatibility.py               # Endpoints legacy (/api/system, /procesos, …)
├── Server-powershell.ps1          # Servidor TCP PowerShell
│
├── database/
│   ├── __init__.py                # SQLAlchemy + Flask-Migrate
│   └── models.py                  # ORM: User, Machine, SystemMetric, Service,
│                                  #       HardwareSnapshot, BackupDestination,
│                                  #       BackupJob, BackupRun, MonitoredService,
│                                  #       ServiceCheck, EmailQueue,
│                                  #       NotificationPreference
│
├── modules/
│   ├── auth/                      # Login, logout, CRUD usuarios, perfil
│   ├── rendimiento/               # CPU, memoria, disco, procesos
│   ├── particiones/               # Discos y particiones
│   ├── backup/                    # Copias de seguridad (routes + services + parsers)
│   ├── machines/                  # Gestión multi-máquina
│   ├── hardware/                  # Inventario de hardware
│   ├── red/                       # Información de red
│   ├── monitorizacion/            # Poller de servicios (probe + poller + routes)
│   ├── notifications/             # Config SMTP y envío de email de prueba
│   └── export/                    # PDF / Excel
│
├── utils/
│   ├── powershell_client.py       # Cliente TCP (con soporte TLS)
│   ├── cache_manager.py           # Caché en memoria, thread-safe
│   ├── background_tasks.py        # Hilo de refresco de métricas
│   ├── encryption.py              # Cifrado Fernet de columnas sensibles
│   ├── mailer.py                  # Envío SMTP síncrono
│   ├── mailer_worker.py           # Worker async con cola y backoff
│   ├── audit.py                   # Registro de auditoría
│   └── validators.py              # Validación de entradas
│
├── templates/
│   ├── auth/                      # login.html, usuarios.html, registros.html
│   ├── emails/                    # _base.html + 6 plantillas de alerta/evento
│   └── *.html                     # index, particiones, backup, hardware,
│                                  # red, monitorizacion, vista_general
│
├── static/
│   ├── css/                       # 8 hojas de estilo (incluye dark.css, vista_general.css)
│   └── js/                        # 11 archivos JS (i18n.js, theme.js, profile_modal.js, …)
│
├── tests/
│   ├── conftest.py                # Fixtures globales
│   ├── unit/                      # 13 archivos (parsers, caché, modelos, cifrado,
│   │                              #   mailer, probe, validators, backup services,
│   │                              #   powershell client, notifications dispatch,
│   │                              #   mailer worker)
│   └── integration/               # 13 archivos (uno por blueprint/módulo)
│
├── migrations/                    # Migraciones Alembic
├── nginx/                         # Configuración nginx + Dockerfile
├── postgres/                      # Configuración PostgreSQL con SSL
├── docs/                          # Documentación y diagramas
│   ├── TESTING.md                 # Guía completa de testing
│   ├── diagrama_clases.md         # Diagrama de clases del proyecto
│   └── Herramienta-Gestion_postman_apis.json         # Colección Postman
├── scripts/                       # Scripts auxiliares
│   ├── run_tests.bat              # Tests en Windows
│   └── run_tests.sh               # Tests en Linux/Mac
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── requirements-dev.txt
└── .env.example
```

## Instalación

### Opción A — Docker (recomendado)

```bash
# 1. Copiar y configurar variables de entorno
cp .env.example .env
# Editar .env: SECRET_KEY, ADMIN_PASSWORD y FIELD_ENCRYPTION_KEY son OBLIGATORIOS

# 2. Levantar servicios (Flask, PostgreSQL, nginx, MailHog)
docker-compose up -d

# 3. Iniciar el servidor PowerShell en el equipo Windows destino (como Administrador)
.\Server-powershell.ps1
```

Acceder en `https://localhost` — El certificado autofirmado generará una advertencia en el navegador la primera vez.

### Opción B — Instalación local

**Requisitos previos**
- Windows 10/11 o Windows Server 2016+
- Python 3.8+
- PostgreSQL 12+
- PowerShell 5.1+
- Privilegios de Administrador (para operaciones de disco)

```bash
# 1. Crear entorno virtual e instalar dependencias
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 2. Configurar entorno
cp .env.example .env
# Editar .env con los valores correspondientes

# 3. Iniciar servidor PowerShell (PowerShell como Administrador)
.\Server-powershell.ps1

# 4. Iniciar servidor Flask
python main.py
```

Acceder en `http://localhost:5000`

## Variables de Entorno

| Variable | Descripción | Requerida |
|----------|-------------|-----------|
| `SECRET_KEY` | Clave de sesión Flask | **Sí** |
| `ADMIN_PASSWORD` | Contraseña del superadmin inicial (mín. 12 caracteres) | **Sí** |
| `FIELD_ENCRYPTION_KEY` | Clave Fernet para cifrado de columnas sensibles. **No cambiar en producción.** | **Sí** |
| `DATABASE_URL` | Cadena de conexión PostgreSQL completa (Railway, Heroku, Docker) | No (si se omite se construye desde los componentes DB_*) |
| `DB_USER` | Usuario PostgreSQL | No (default: `gestion`) |
| `DB_PASSWORD` | Contraseña PostgreSQL | **Sí** (obligatoria si no hay `DATABASE_URL`) |
| `DB_HOST` | Host PostgreSQL | No (default: `localhost`) |
| `DB_PORT` | Puerto PostgreSQL | No (default: `5432`) |
| `DB_NAME` | Nombre de la base de datos | No (default: `gestion_db`) |
| `POWERSHELL_SERVER` | IP del servidor PowerShell | No (default: `127.0.0.1`) |
| `POWERSHELL_PORT` | Puerto TCP del servidor PowerShell | No (default: `12345`) |
| `SOCKET_TIMEOUT` | Timeout de conexión en segundos | No (default: `3`; el `.env.example` usa `10` — recomendado para redes lentas) |
| `CACHE_TIME` | TTL de caché en segundos | No (default: `3`) |
| `BACKUP_PATH` | Ruta por defecto para los backups en el servidor PowerShell | No (default: `C:\Backups`) |
| `PARTITION_OPS` | Habilitar operaciones de escritura en particiones (`True`/`False`) | No (default: `True`) |
| `FLASK_ENV` | Entorno Flask; `production` activa HTTPS forzado (Talisman) | No |
| `FLASK_DEBUG` | Modo debug de Flask | No (default: `False`) |
| `FLASK_SKIP_DB_INIT` | Omite migraciones y bootstrap al arrancar (usar durante `flask db migrate`) | No (default: `false`) |
| `CORS_ALLOWED_ORIGINS` | Orígenes CORS permitidos (coma-separados) | No (default: `http://localhost:5000`) |
| `ADMIN_USER` | Nombre de usuario del superadmin inicial | No (default: `admin`) |
| `METRICS_RETENTION_DAYS` | Retención de métricas históricas en días | No (default: `30`) |
| `PS_TLS_ENABLED` | Habilitar TLS para conexión PowerShell | No (default: `false`) |
| `PS_SERVER_CA_CERT` | Ruta al certificado CA para TLS | No |
| `MAIL_ENABLED` | Habilitar notificaciones por email | No (default: `false`) |
| `SMTP_HOST` | Servidor SMTP | No (default: `localhost`; en Docker usa `mailhog`) |
| `SMTP_PORT` | Puerto SMTP | No (default: `25`; en Docker con MailHog usa `1025`) |
| `SMTP_USER` | Usuario SMTP | No |
| `SMTP_PASSWORD` | Contraseña SMTP | No |
| `SMTP_USE_TLS` | STARTTLS (puerto 587) | No (default: `false`) |
| `SMTP_USE_SSL` | SMTPS (puerto 465) | No (default: `false`) |
| `SMTP_TIMEOUT` | Timeout SMTP en segundos | No (default: `10`) |
| `MAIL_FROM` | Dirección remitente | No (default: `alertas@gestion.local`) |
| `MAIL_FROM_NAME` | Nombre del remitente | No (default: `Control Remoto Windows`) |

Generar claves seguras:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Ver `.env.example` para la lista completa con valores de ejemplo.

## API REST

La columna **Rol mínimo** indica el nivel más bajo que puede acceder al endpoint. Orden ascendente: `solo_lectura` → `operador` → `admin` → `superadmin`. **Autenticado** = cualquier usuario con sesión activa. **—** = endpoint público (sin sesión).

### Sistema y Rendimiento
| Método | Ruta | Descripción | Rol mínimo |
|--------|------|-------------|------------|
| GET | `/api/system` | Métricas CPU, memoria y disco (caché local o remoto) | Autenticado |
| GET | `/api/rendimiento/system` | Ídem vía blueprint modular | Autenticado |
| GET | `/health` | Estado del servidor Flask | — |
| GET | `/health/powershell` | Conectividad con el servidor PowerShell | Autenticado |
| GET | `/health/background` | Estado del hilo de refresco de métricas | Autenticado |
| GET | `/procesos?action=listar` | Lista de procesos activos | Autenticado |

### Particiones
| Método | Ruta | Descripción | Rol mínimo |
|--------|------|-------------|------------|
| GET | `/api/particiones/disks` | Discos físicos (uso enriquecido con datos de particiones) | Autenticado |
| GET | `/api/particiones/partitions` | Particiones; `?disk_id=disk0` filtra por disco | Autenticado |
| GET | `/api/particiones/disk_detail?disk_id=<id>` | Detalle de disco físico | Autenticado |
| POST | `/api/particiones/partition_operation` | Operaciones de escritura — campo `operation` ∈ {`create`, `format`, `delete`, `resize`} | admin+ |

### Backup — Destinos
| Método | Ruta | Descripción | Rol mínimo |
|--------|------|-------------|------------|
| GET | `/api/backup/destinations` | Listar destinos de backup | operador+ |
| POST | `/api/backup/destinations` | Crear destino | admin+ |
| PUT | `/api/backup/destinations/<id>` | Editar destino | admin+ |
| DELETE | `/api/backup/destinations/<id>` | Eliminar destino (falla si tiene trabajos asociados) | admin+ |
| POST | `/api/backup/destinations/<id>/test` | Verificar accesibilidad del destino | operador+ |

### Backup — Trabajos
| Método | Ruta | Descripción | Rol mínimo |
|--------|------|-------------|------------|
| GET | `/api/backup/jobs` | Listar trabajos configurados (sincroniza Task Scheduler) | operador+ |
| POST | `/api/backup/jobs` | Crear trabajo de backup | admin+ |
| PUT | `/api/backup/jobs/<id>` | Editar trabajo | admin+ |
| DELETE | `/api/backup/jobs/<id>` | Eliminar trabajo (historial se conserva huérfano) | admin+ |
| POST | `/api/backup/jobs/<id>/toggle` | Activar / desactivar trabajo | admin+ |
| POST | `/api/backup/jobs/<id>/run` | Ejecutar trabajo ahora (devuelve 202 + run) | operador+ |
| POST | `/api/backup/jobs/<id>/run_scheduled` | Forzar la tarea de Windows Task Scheduler asociada | admin+ |
| GET | `/api/backup/jobs/<id>/scheduled_log` | Log de la tarea programada en Windows | operador+ |

### Backup — Historial y Operaciones
| Método | Ruta | Descripción | Rol mínimo |
|--------|------|-------------|------------|
| GET | `/api/backup/history` | Historial paginado; `?limit=&offset=&q=` | operador+ |
| GET | `/api/backup/history/<id>` | Detalle de ejecución | operador+ |
| POST | `/api/backup/history/<id>/restore` | Restaurar backup completado a una ruta | admin+ |
| DELETE | `/api/backup/history/<id>` | Eliminar registro (`?delete_disk=1` borra también el archivo) | admin+ |
| POST | `/api/backup/history/<id>/verify` | Verificar integridad del archivo de backup | operador+ |
| GET | `/api/backup/runs/<id>` | Detalle de run (alias alternativo) | operador+ |
| GET | `/api/backup/summary` | Resumen por máquina (total jobs, último backup, espacio usado) | operador+ |
| GET | `/api/backup/scheduled` | Tareas en Windows Task Scheduler | operador+ |
| POST | `/api/backup/compress` | Comprimir archivos | admin+ |
| POST | `/api/backup/decompress` | Descomprimir archivos | admin+ |
| GET | `/api/backup/list?path=<ruta>` | Lista cruda de backups en el filesystem (legacy) | operador+ |
| GET | `/api/backup/status` | Estado de operaciones en curso | operador+ |

### Monitorización de Servicios
| Método | Ruta | Descripción | Rol mínimo |
|--------|------|-------------|------------|
| GET | `/api/monitorizacion/services` | Listar servicios monitorizados | Autenticado |
| POST | `/api/monitorizacion/services` | Añadir servicio | admin+ |
| PUT | `/api/monitorizacion/services/<id>` | Editar servicio | admin+ |
| DELETE | `/api/monitorizacion/services/<id>` | Eliminar servicio | admin+ |
| POST | `/api/monitorizacion/services/<id>/check` | Sondear servicio ahora | operador+ |
| GET | `/api/monitorizacion/activity` | Actividad reciente (cambios de estado) | Autenticado |
| GET | `/api/monitorizacion/summary` | Resumen de máquinas y servicios | Autenticado |
| GET | `/api/machines` | Listar máquinas gestionadas (ver sección Gestión Multi-Máquina) | Autenticado |
| POST | `/api/monitorizacion/machines` | Añadir máquina | operador+ |
| PUT | `/api/monitorizacion/machines/<id>` | Editar máquina | operador+ |
| DELETE | `/api/monitorizacion/machines/<id>` | Eliminar máquina | operador+ |

### Hardware
| Método | Ruta | Descripción | Rol mínimo |
|--------|------|-------------|------------|
| GET | `/api/hardware/snapshot` | Último snapshot guardado en BD (sin llamada PowerShell) | Autenticado |
| POST | `/api/hardware/refresh` | Refresco en vivo y guardado en BD | operador+ |
| GET | `/api/hardware/memory/live` | RAM en vivo (sondeo ligero, sin BD) | Autenticado |
| GET | `/api/hardware/system` | Información del sistema | Autenticado |
| GET | `/api/hardware/cpu` | CPU (modelo, núcleos, hilos, sockets) | Autenticado |
| GET | `/api/hardware/memory` | Memoria (total, usado, libre, velocidad, slots) | Autenticado |
| GET | `/api/hardware/disks` | Discos (modelo, tipo, temperatura, capacidad) | Autenticado |
| GET | `/api/hardware/gpu` | GPU(s) | Autenticado |
| GET | `/api/hardware/motherboard` | Placa base | Autenticado |
| GET | `/api/hardware/devices` | Dispositivos conectados | Autenticado |
| GET | `/api/hardware/export` | Descarga JSON del inventario completo | Autenticado |

### Red
| Método | Ruta | Descripción | Rol mínimo |
|--------|------|-------------|------------|
| GET | `/api/red/adapters` | Adaptadores de red | Autenticado |
| GET | `/api/red/adapter_details?adapter=<nombre>` | Detalles TCP/IP de un adaptador | Autenticado |
| GET | `/api/red/stats` | Estadísticas de tráfico (RX/TX) | Autenticado |
| GET | `/api/red/activity` | Eventos recientes de red | Autenticado |
| GET | `/api/red/alerts` | Alertas de red | Autenticado |
| POST | `/api/red/tool` | Diagnóstico — `tool` ∈ {`ping`, `traceroute`, `ipconfig`, `netstat`} (operador+); {`release_renew`, `flush_dns`} (admin+) | operador+ |

### Exportación
| Método | Ruta | Descripción | Rol mínimo |
|--------|------|-------------|------------|
| GET | `/api/export/hardware?format=xlsx\|pdf` | Inventario de hardware (multi-máquina con `?machine_id=1&machine_id=2`) | Autenticado |
| GET | `/api/export/rendimiento?format=xlsx\|pdf&days=<n>` | Historial de métricas (máx. 30 días) | Autenticado |
| GET | `/api/export/particiones?format=xlsx\|pdf` | Discos físicos y particiones | Autenticado |
| GET | `/api/export/red?format=xlsx\|pdf` | Adaptadores y estadísticas de red | Autenticado |

### Autenticación y Usuarios
| Método | Ruta | Descripción | Rol mínimo |
|--------|------|-------------|------------|
| GET/POST | `/auth/login` | Login (POST: 5/min, 20/h; superar el límite bloquea la cuenta 10 min) | — |
| GET | `/auth/logout` | Logout | Autenticado |
| GET | `/auth/usuarios` | Página de gestión de usuarios | admin+ |
| GET | `/auth/registros` | Página de audit log | admin+ |
| GET | `/auth/api/usuarios` | Listar usuarios | admin+ |
| POST | `/auth/api/usuarios` | Crear usuario (envía email de bienvenida) | superadmin |
| PUT | `/auth/api/usuarios/<id>` | Editar usuario (admin no puede modificar superadmins ni cambiar roles) | admin+ |
| DELETE | `/auth/api/usuarios/<id>` | Eliminar usuario | superadmin |
| POST | `/auth/api/usuarios/<id>/unlock` | Desbloquear cuenta manualmente | admin+ |
| GET | `/auth/api/registros` | Audit log JSON con filtros y paginación | admin+ |
| GET | `/auth/api/registros/export?format=csv\|xlsx\|pdf` | Exportar registros de auditoría | admin+ |
| GET | `/auth/api/profile` | Perfil del usuario autenticado | Autenticado |
| POST | `/auth/api/profile/update` | Actualizar perfil (email, nombre, idioma, tema, avatar) | Autenticado |
| GET | `/auth/api/profile/notifications` | Preferencias de notificación | Autenticado |
| POST | `/auth/api/profile/notifications` | Actualizar preferencias de notificación | Autenticado |
| POST | `/auth/api/profile/password` | Cambiar contraseña (encola email de aviso) | Autenticado |

### Notificaciones
| Método | Ruta | Descripción | Rol mínimo |
|--------|------|-------------|------------|
| GET | `/api/notifications/config` | Configuración SMTP actual | superadmin |
| POST | `/api/notifications/test` | Enviar email de prueba | superadmin |

### Gestión Multi-Máquina
| Método | Ruta | Descripción | Rol mínimo |
|--------|------|-------------|------------|
| GET | `/api/machines` | Listar máquinas registradas | Autenticado |
| POST | `/api/machines` | Registrar nueva máquina | operador+ |
| PUT | `/api/machines/<id>` | Editar máquina | operador+ |
| DELETE | `/api/machines/<id>` | Eliminar máquina | operador+ |
| POST | `/api/machines/<id>/ping` | Comprobar conectividad TCP y actualizar estado | operador+ |
| POST | `/api/machines/ping_all` | Sondear todas las máquinas en paralelo | operador+ |
| GET | `/api/machines/<id>/metrics` | Historial de métricas de la máquina (`?hours=1`, máx. 168) | Autenticado |
| GET | `/api/machines/<id>/services` | Servicios Windows conocidos de la máquina | Autenticado |

## Testing

```bash
# Instalar dependencias de desarrollo
pip install -r requirements-dev.txt

# Ejecutar todos los tests
pytest

# Con reporte de cobertura
pytest --cov=. --cov-report=html

# Scripts de conveniencia
scripts\run_tests.bat      # Windows
./scripts/run_tests.sh     # Linux/Mac
```

El proyecto cuenta con **13 archivos de tests unitarios** (parsers de backup, particiones y rendimiento; caché; cifrado; mailer; mailer worker; probe; validators; modelos; powershell client; notifications dispatch; backup services) y **13 archivos de tests de integración** (uno por blueprint/módulo: auth, particiones, backup, backup history, hardware, red, rendimiento, machines, monitorizacion, export, notifications, audit/machine, api endpoints). La cobertura se mide con branch coverage (`branch = True`); el umbral configurado es ≥ 75 % (`fail_under = 75` en `pytest.ini`), sobre los módulos `modules/`, `utils/`, `main.py` y `config.py`. Ver [docs/TESTING.md](docs/TESTING.md) para la guía completa.

## Seguridad

- **HTTPS** obligatorio en producción (nginx con TLS 1.2+)
- **CSRF** en formularios HTML (Flask-WTF + inyección via `csrf.js`); los blueprints de API JSON (`rendimiento`, `particiones`, `backup`, `machines`, `hardware`, `red`, `compat`, `export`, `monitorizacion`, `notifications`) están exentos mediante `csrf.exempt()` — su protección equivalente son SameSite=Lax + CORS restringido + cabecera `X-CSRFToken`; el blueprint `auth` NO está exento (el formulario de login usa verificación WTF estándar)
- **Rate limiting** en login: 5 req/min, 20 req/hora
- **Bloqueo por intentos fallidos (15 min)**: tras 5 intentos fallidos consecutivos → `locked_until = ahora + 15 min`; se resetea al hacer login correcto; desbloqueable manualmente vía `POST /auth/api/usuarios/<id>/unlock`
- **Bloqueo por rate-limit (10 min)**: cuando Flask-Limiter devuelve 429 en `/auth/login`, el manejador de error escribe `locked_until = ahora + 10 min` en la cuenta (si el username está en el formulario); impide sortear el bloqueo cambiando de IP; registrado como `login_blocked_ratelimit` en el audit log
- **Tiempo constante en login**: hash dummy para evitar enumeración de usuarios por latencia
- **Cifrado en reposo**: campos PII (email, nombre) y cuerpos de email cifrados con Fernet (AES-128-CBC + HMAC-SHA256). Clave gestionada por `FIELD_ENCRYPTION_KEY`
- **Sesión**: duración máxima de 8 horas; cierre automático por inactividad (30 min)
- **Headers de seguridad**: CSP, HSTS (1 año + subdominios), X-Frame-Options DENY, X-Content-Type-Options, Referrer-Policy
- **Cookies**: HttpOnly, SameSite=Lax, Secure en producción
- **CORS**: orígenes configurables vía `CORS_ALLOWED_ORIGINS`
- **TLS opcional** para la conexión TCP al servidor PowerShell
- **Auditoría**: registro de todas las acciones administrativas y accesos en `logs/audit.log`

Para entornos de producción:
1. Generar `SECRET_KEY` y `FIELD_ENCRYPTION_KEY` con `python -c "import secrets; print(secrets.token_hex(32))"`
2. **No cambiar `FIELD_ENCRYPTION_KEY` una vez en producción** — los datos existentes quedarían ilegibles
3. Usar contraseña de administrador con al menos 12 caracteres, mayúsculas, números y caracteres especiales
4. Establecer `FLASK_ENV=production` para activar HTTPS forzado
5. Habilitar TLS para la conexión PowerShell si la comunicación atraviesa redes no confiables
6. Restringir el puerto 12345 mediante firewall al servidor Flask únicamente

## Postman

El archivo `docs/Herramienta-Gestion_postman_apis.json` incluye todos los endpoints documentados listos para importar en Postman.

## Licencia

Uso educativo e interno. Revisar términos de licenciamiento según necesidades de despliegue.
