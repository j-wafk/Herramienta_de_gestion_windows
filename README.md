# Herramienta de Gestión Remota para Windows

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
- Crear, formatear (NTFS / FAT32 / exFAT), eliminar y montar particiones
- Clonación, conversión MBR↔GPT, montaje de imágenes ISO/VHD

### Copias de Seguridad
- Tipos: Completo, Incremental, Diferencial
- Compresión ZIP (4 niveles), restauración, verificación de integridad
- Trabajos de backup configurables con destinos locales, de red o FTP
- Programación mediante Windows Task Scheduler (diario / semanal / mensual)
- Historial de ejecuciones con progreso en tiempo real y preservación tras eliminación del trabajo

### Monitorización de Servicios
- Poller en background para endpoints TCP y UDP con icono por tipo de servicio (WinRM, IIS, SQL, RDP, DNS, API…)
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

### Autenticación y Control de Acceso
- Login con rate limiting (5 req/min, 20 req/hora)
- Bloqueo automático de cuenta tras 5 intentos fallidos (15 minutos)
- Protección contra enumeración de usuarios mediante verificación en tiempo constante
- Sesión permanente de 8 horas con cierre automático por inactividad (30 min)
- Cuatro roles: `superadmin`, `admin`, `operador`, `solo_lectura`
- Perfiles de usuario: nombre completo, email cifrado, idioma, tema, color de avatar, preferencias de notificación
- Auditoría completa de acciones administrativas con log en `logs/audit.log`

### Notificaciones por Email
- Cola persistente en base de datos con reintentos y backoff exponencial
- Plantillas HTML para: bienvenida, cambio de contraseña, backup completado/fallido, máquina offline, servicio caído, prueba
- Preferencias por usuario: machine_offline, service_down, backup_failed, backup_completed, resumen_diario
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
- Reportes en PDF y Excel con rangos de fecha configurables

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
│   ├── unit/                      # 10 archivos (parsers, caché, modelos, cifrado,
│   │                              #   mailer, probe, validators, backup services)
│   └── integration/               # 13 archivos (un archivo por blueprint/módulo)
│
├── migrations/                    # Migraciones Alembic
├── nginx/                         # Configuración nginx + Dockerfile
├── postgres/                      # Configuración PostgreSQL con SSL
├── docs/                          # Documentación y diagramas
│   ├── TESTING.md                 # Guía completa de testing
│   ├── diagrama_clases.md         # Diagrama de clases del proyecto
│   └── Herramienta-Gestion.postman_collection.json  # Colección Postman
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
| `DATABASE_URL` | Cadena de conexión PostgreSQL | No (default: local) |
| `POWERSHELL_SERVER` | IP del servidor PowerShell | No (default: 127.0.0.1) |
| `POWERSHELL_PORT` | Puerto TCP del servidor PowerShell | No (default: 12345) |
| `SOCKET_TIMEOUT` | Timeout de conexión en segundos | No (default: 3) |
| `CACHE_TIME` | TTL de caché en segundos | No (default: 3) |
| `FLASK_DEBUG` | Modo debug | No (default: False) |
| `CORS_ALLOWED_ORIGINS` | Orígenes CORS permitidos (coma-separados) | No (default: http://localhost:5000) |
| `ADMIN_USER` | Nombre de usuario del superadmin inicial | No (default: admin) |
| `METRICS_RETENTION_DAYS` | Retención de métricas históricas en días | No (default: 30) |
| `PS_TLS_ENABLED` | Habilitar TLS para conexión PowerShell | No (default: false) |
| `PS_SERVER_CA_CERT` | Ruta al certificado CA para TLS | No |
| `MAIL_ENABLED` | Habilitar notificaciones por email | No (default: false) |
| `SMTP_HOST` | Servidor SMTP | No (default: localhost) |
| `SMTP_PORT` | Puerto SMTP | No (default: 25) |
| `SMTP_USER` | Usuario SMTP | No |
| `SMTP_PASSWORD` | Contraseña SMTP | No |
| `SMTP_USE_TLS` | STARTTLS (puerto 587) | No (default: false) |
| `SMTP_USE_SSL` | SMTPS (puerto 465) | No (default: false) |
| `SMTP_TIMEOUT` | Timeout SMTP en segundos | No (default: 10) |
| `MAIL_FROM` | Dirección remitente | No (default: alertas@gestion.local) |
| `MAIL_FROM_NAME` | Nombre del remitente | No (default: Control Remoto Windows) |

Generar claves seguras:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Ver `.env.example` para la lista completa con valores de ejemplo.

## API REST

### Sistema y Rendimiento
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/system` | Métricas CPU, memoria y disco (caché local o remoto) |
| GET | `/api/rendimiento/system` | Ídem vía blueprint modular |
| GET | `/health` | Estado del servidor Flask |
| GET | `/health/powershell` | Conectividad con el servidor PowerShell |
| GET | `/health/background` | Estado del hilo de refresco de métricas |
| GET | `/procesos?action=listar` | Lista de procesos activos |

### Particiones
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/particiones/disks` | Discos físicos |
| GET | `/api/particiones/partitions` | Particiones |
| GET | `/api/particiones/disk/<id>/details` | Detalle de disco |
| POST | `/api/particiones/create` | Crear partición |
| POST | `/api/particiones/format` | Formatear partición |
| POST | `/api/particiones/delete` | Eliminar partición |
| POST | `/api/particiones/clone` | Clonar disco |
| POST | `/api/particiones/convert` | Convertir MBR/GPT |

### Backup
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/backup/destinations` | Destinos de backup |
| POST | `/api/backup/destinations` | Crear destino |
| GET | `/api/backup/jobs` | Listar trabajos configurados |
| POST | `/api/backup/jobs` | Crear trabajo de backup |
| POST | `/api/backup/jobs/<id>/run` | Ejecutar trabajo ahora |
| DELETE | `/api/backup/jobs/<id>` | Eliminar trabajo |
| GET | `/api/backup/runs` | Historial de ejecuciones |
| POST | `/api/backup/create` | Crear backup ad-hoc |
| POST | `/api/backup/restore` | Restaurar backup |
| POST | `/api/backup/verify` | Verificar integridad |
| POST | `/api/backup/compress` | Comprimir archivos |
| POST | `/api/backup/decompress` | Descomprimir archivos |
| POST | `/api/backup/schedule` | Programar backup en Task Scheduler |
| GET | `/api/backup/status` | Estado de operaciones en curso |

### Monitorización de Servicios
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/monitorizacion/services` | Listar servicios monitorizados |
| POST | `/api/monitorizacion/services` | Añadir servicio |
| PUT | `/api/monitorizacion/services/<id>` | Editar servicio |
| DELETE | `/api/monitorizacion/services/<id>` | Eliminar servicio |
| POST | `/api/monitorizacion/services/<id>/check` | Sondear servicio ahora |
| GET | `/api/monitorizacion/activity` | Actividad reciente (cambios de estado) |
| GET | `/api/monitorizacion/machines` | Máquinas gestionadas |
| POST | `/api/monitorizacion/machines` | Añadir máquina |
| PUT | `/api/monitorizacion/machines/<id>` | Editar máquina |
| DELETE | `/api/monitorizacion/machines/<id>` | Eliminar máquina |

### Autenticación y Usuarios
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET/POST | `/auth/login` | Login |
| GET | `/auth/logout` | Logout |
| GET | `/auth/usuarios` | Página de gestión de usuarios |
| POST | `/auth/api/users` | Crear usuario |
| PUT | `/auth/api/users/<id>` | Editar usuario |
| DELETE | `/auth/api/users/<id>` | Eliminar usuario |
| GET | `/auth/api/profile` | Obtener perfil del usuario actual |
| PUT | `/auth/api/profile` | Actualizar perfil |
| POST | `/auth/api/profile/avatar` | Subir avatar |
| GET | `/auth/api/registros` | Log de auditoría |
| GET | `/auth/api/notification-preferences` | Preferencias de notificación |
| PUT | `/auth/api/notification-preferences` | Actualizar preferencias |

### Notificaciones
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/notifications/config` | Configuración SMTP actual (superadmin) |
| POST | `/api/notifications/test` | Enviar email de prueba (superadmin) |

### Otros
| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/command` | Ejecutar comando PowerShell (lista blanca) |
| GET | `/api/machines` | Listar máquinas registradas |
| GET | `/api/hardware` | Información de hardware |
| GET | `/api/red` | Configuración de red |
| GET | `/api/export/pdf` | Exportar reporte PDF |
| GET | `/api/export/excel` | Exportar reporte Excel |

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

El proyecto cuenta con **10 archivos de tests unitarios** (parsers, caché, cifrado, mailer, modelos, probe, validators, backup services) y **13 archivos de tests de integración** (uno por blueprint/módulo). Ver [docs/TESTING.md](docs/TESTING.md) para la guía completa.

## Seguridad

- **HTTPS** obligatorio en producción (nginx con TLS 1.2+)
- **CSRF** en todos los formularios (Flask-WTF + inyección via `csrf.js`)
- **Rate limiting** en login: 5 req/min, 20 req/hora
- **Bloqueo de cuenta**: 5 intentos fallidos → bloqueo automático de 15 minutos
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

El archivo `docs/Herramienta-Gestion.postman_collection.json` incluye todos los endpoints documentados listos para importar en Postman.

## Licencia

Uso educativo e interno. Revisar términos de licenciamiento según necesidades de despliegue.
