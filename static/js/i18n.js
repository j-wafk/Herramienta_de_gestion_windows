/* i18n.js — Sistema de traducciones ES/EN para toda la aplicación.
 *
 * Uso en HTML:  <span data-i18n="nav.overview"></span>
 * La función window.i18n.apply(lang) rellena esos elementos.
 * window.i18n.t(key) devuelve la cadena traducida.
 *
 * El idioma activo se lee de document.documentElement.lang.
 * Se aplica automáticamente en DOMContentLoaded.
 */
(function () {
    'use strict';

    var TRANSLATIONS = {
        es: {
            // Sidebar
            'nav.overview':     'Vista General',
            'nav.performance':  'Rendimiento',
            'nav.hardware':     'Hardware',
            'nav.users':        'Usuarios y Permisos',
            'nav.partitions':   'Particiones de Disco',
            'nav.network':      'Configuración de Red',
            'nav.logs':         'Registros del Sistema',
            'nav.backup':       'Copias de Seguridad',
            'nav.monitoring':   'Monitorización',
            // Header
            'header.logout':        'Cerrar sesión',
            'header.connected':     'CONECTADO',
            'header.disconnected':  'DESCONECTADO',
            'header.title':         'Control Remoto para Windows',
            // Footer
            'footer.lastUpdate': 'Última actualización:',
            'footer.refreshNow': 'Actualizar ahora',
            'footer.timezone':   'Zona horaria:',
            // Sidebar máquina
            'sidebar.device': 'Equipo:',
            // Página Vista General
            'page.overview':     'Vista General del Sistema',
            'vg.memory':         'Memoria',
            'vg.storage':        'Almacenamiento',
            'vg.generalStatus':  'Estado General',
            'vg.freeStorage':    'Espacio libre disponible',
            'vg.sysInfo':        'Información del Equipo',
            'vg.generalPerf':    'Rendimiento General',
            'vg.mainServices':   'Servicios Principales',
            'vg.recentActivity': 'Actividad Reciente',
            'vg.alerts':         'Alertas y Seguridad',
            'vg.quickActions':   'Acciones Rápidas',
            'vg.loading':        'Cargando...',
            'vg.seeAllEvents':   'Ver todos los eventos...',
            'vg.perfAvg':        'Uso promedio · Últimos 15 minutos',
            // Info table Vista General
            'info.hostname':    'Hostname',
            'info.os':          'Sistema Operativo',
            'info.lastBoot':    'Último reinicio',
            'info.ip':          'Dirección IP',
            'info.activeUser':  'Usuario activo',
            'info.uptime':      'Uptime',
            // Quick actions
            'qa.refresh':       'Actualizar',
            'qa.viewProcesses': 'Ver Procesos',
            'qa.openLogs':      'Abrir Registros',
            'qa.runBackup':     'Ejecutar Backup',
            'qa.checkNetwork':  'Revisar Red',
            // Otras páginas — títulos
            'page.performance':  'Rendimiento del Sistema',
            'page.hardware':     'Información de Hardware',
            'page.partitions':   'Particiones de Disco',
            'page.network':      'Configuración de Red',
            'page.monitoring':   'Monitorización de Servicios',
            'page.backup':       'Copias de Seguridad',
            'page.users':        'Gestión de Usuarios',
            'page.logs':         'Registros del Sistema',
            // Login
            'login.title':      'Iniciar sesión',
            'login.subtitle':   'Accede con tus credenciales de administrador',
            'login.username':   'Usuario',
            'login.password':   'Contraseña',
            'login.button':     'Entrar',
            // Profile modal
            'pm.tabInfo':       'Información',
            'pm.tabSecurity':   'Seguridad',
            'pm.tabPrefs':      'Preferencias',
            'pm.avatar':        'Avatar',
            'pm.fullName':      'Nombre completo',
            'pm.fullNamePh':    'Tu nombre completo',
            'pm.email':         'Correo electrónico',
            'pm.emailPh':       'correo@ejemplo.com',
            'pm.username':      'Usuario',
            'pm.role':          'Rol',
            'pm.lastLogin':     'Último acceso',
            'pm.memberSince':   'Miembro desde',
            'pm.saveChanges':   'Guardar cambios',
            'pm.currentPass':   'Contraseña actual',
            'pm.currentPassPh': 'Contraseña actual',
            'pm.newPass':       'Nueva contraseña',
            'pm.newPassPh':     'Mín. 12 caracteres',
            'pm.confirmPass':   'Confirmar nueva contraseña',
            'pm.confirmPassPh': 'Repite la nueva contraseña',
            'pm.changePass':    'Cambiar contraseña',
            'pm.language':      'Idioma',
            'pm.theme':         'Tema de interfaz',
            'pm.themeLight':    'Claro',
            'pm.themeDark':     'Oscuro',
            'pm.emailNotif':    'Notificaciones por email',
            'pm.emailNotifSub': 'Recibir alertas del sistema por correo',
            'pm.notifEvents':            'Eventos que disparan email',
            'pm.notifEventsSub':         'Elige qué eventos te notifican por correo',
            'pm.notifMachineOffline':    'Máquina sin conexión',
            'pm.notifMachineOfflineSub': 'Cuando una máquina deja de responder',
            'pm.notifServiceDown':       'Servicio caído',
            'pm.notifServiceDownSub':    'Cuando un servicio monitorizado pasa a down',
            'pm.notifBackupFailed':      'Backup fallido',
            'pm.notifBackupFailedSub':   'Cuando una copia de seguridad falla',
            'pm.notifBackupCompleted':   'Backup completado',
            'pm.notifBackupCompletedSub':'Cuando una copia de seguridad termina con éxito',
            'pm.notifDailySummary':      'Resumen diario',
            'pm.notifDailySummarySub':   'Recibir un email diario con el estado general',
            'pm.savePrefs':     'Guardar preferencias',
            'pm.close':         'Cerrar',
            'pm.never':         'Nunca',
            // Strength
            'pw.veryWeak':   'Muy débil',
            'pw.weak':       'Débil',
            'pw.fair':       'Aceptable',
            'pw.strong':     'Fuerte',
            'pw.veryStrong': 'Muy fuerte',
            // Messages
            'msg.saved':       'Cambios guardados correctamente',
            'msg.prefsSaved':  'Preferencias guardadas',
            'msg.passChanged': 'Contraseña cambiada correctamente',
            'msg.connError':   'Error de conexión',
            'msg.saveError':   'Error al guardar',
            'msg.passError':   'Error al cambiar contraseña',
        },

        en: {
            // Sidebar
            'nav.overview':     'Overview',
            'nav.performance':  'Performance',
            'nav.hardware':     'Hardware',
            'nav.users':        'Users & Permissions',
            'nav.partitions':   'Disk Partitions',
            'nav.network':      'Network Config',
            'nav.logs':         'System Logs',
            'nav.backup':       'Backups',
            'nav.monitoring':   'Monitoring',
            // Header
            'header.logout':       'Sign out',
            'header.connected':    'CONNECTED',
            'header.disconnected': 'DISCONNECTED',
            'header.title':        'Windows Remote Manager',
            // Footer
            'footer.lastUpdate': 'Last update:',
            'footer.refreshNow': 'Refresh now',
            'footer.timezone':   'Timezone:',
            // Sidebar machine
            'sidebar.device': 'Device:',
            // Overview page
            'page.overview':     'System Overview',
            'vg.memory':         'Memory',
            'vg.storage':        'Storage',
            'vg.generalStatus':  'Overall Status',
            'vg.freeStorage':    'Free disk space',
            'vg.sysInfo':        'System Information',
            'vg.generalPerf':    'General Performance',
            'vg.mainServices':   'Key Services',
            'vg.recentActivity': 'Recent Activity',
            'vg.alerts':         'Alerts & Security',
            'vg.quickActions':   'Quick Actions',
            'vg.loading':        'Loading...',
            'vg.seeAllEvents':   'View all events...',
            'vg.perfAvg':        'Average usage · Last 15 minutes',
            // Info table
            'info.hostname':    'Hostname',
            'info.os':          'Operating System',
            'info.lastBoot':    'Last reboot',
            'info.ip':          'IP Address',
            'info.activeUser':  'Active user',
            'info.uptime':      'Uptime',
            // Quick actions
            'qa.refresh':       'Refresh',
            'qa.viewProcesses': 'View Processes',
            'qa.openLogs':      'Open Logs',
            'qa.runBackup':     'Run Backup',
            'qa.checkNetwork':  'Check Network',
            // Page titles
            'page.performance':  'System Performance',
            'page.hardware':     'Hardware Information',
            'page.partitions':   'Disk Partitions',
            'page.network':      'Network Configuration',
            'page.monitoring':   'Service Monitoring',
            'page.backup':       'Backups',
            'page.users':        'User Management',
            'page.logs':         'System Logs',
            // Login
            'login.title':    'Sign in',
            'login.subtitle': 'Access with your administrator credentials',
            'login.username': 'Username',
            'login.password': 'Password',
            'login.button':   'Sign in',
            // Profile modal
            'pm.tabInfo':       'Information',
            'pm.tabSecurity':   'Security',
            'pm.tabPrefs':      'Preferences',
            'pm.avatar':        'Avatar',
            'pm.fullName':      'Full name',
            'pm.fullNamePh':    'Your full name',
            'pm.email':         'Email address',
            'pm.emailPh':       'email@example.com',
            'pm.username':      'Username',
            'pm.role':          'Role',
            'pm.lastLogin':     'Last login',
            'pm.memberSince':   'Member since',
            'pm.saveChanges':   'Save changes',
            'pm.currentPass':   'Current password',
            'pm.currentPassPh': 'Current password',
            'pm.newPass':       'New password',
            'pm.newPassPh':     'Min. 12 characters',
            'pm.confirmPass':   'Confirm new password',
            'pm.confirmPassPh': 'Repeat new password',
            'pm.changePass':    'Change password',
            'pm.language':      'Language',
            'pm.theme':         'Interface theme',
            'pm.themeLight':    'Light',
            'pm.themeDark':     'Dark',
            'pm.emailNotif':    'Email notifications',
            'pm.emailNotifSub': 'Receive system alerts by email',
            'pm.notifEvents':            'Events that trigger email',
            'pm.notifEventsSub':         'Choose which events notify you by email',
            'pm.notifMachineOffline':    'Machine offline',
            'pm.notifMachineOfflineSub': 'When a machine stops responding',
            'pm.notifServiceDown':       'Service down',
            'pm.notifServiceDownSub':    'When a monitored service goes down',
            'pm.notifBackupFailed':      'Backup failed',
            'pm.notifBackupFailedSub':   'When a backup job fails',
            'pm.notifBackupCompleted':   'Backup completed',
            'pm.notifBackupCompletedSub':'When a backup job completes successfully',
            'pm.notifDailySummary':      'Daily summary',
            'pm.notifDailySummarySub':   'Receive a daily email with overall status',
            'pm.savePrefs':     'Save preferences',
            'pm.close':         'Close',
            'pm.never':         'Never',
            // Strength
            'pw.veryWeak':   'Very weak',
            'pw.weak':       'Weak',
            'pw.fair':       'Fair',
            'pw.strong':     'Strong',
            'pw.veryStrong': 'Very strong',
            // Messages
            'msg.saved':       'Changes saved successfully',
            'msg.prefsSaved':  'Preferences saved',
            'msg.passChanged': 'Password changed successfully',
            'msg.connError':   'Connection error',
            'msg.saveError':   'Error saving',
            'msg.passError':   'Error changing password',
        },
    };

    var _currentLang = 'es';

    function _t(key) {
        var dict = TRANSLATIONS[_currentLang] || TRANSLATIONS['es'];
        return dict[key] !== undefined ? dict[key]
             : (TRANSLATIONS['es'][key] !== undefined ? TRANSLATIONS['es'][key] : key);
    }

    function _apply(lang) {
        _currentLang = lang || document.documentElement.lang || 'es';
        document.querySelectorAll('[data-i18n]').forEach(function (el) {
            var key = el.getAttribute('data-i18n');
            var attr = el.getAttribute('data-i18n-attr');
            var val  = _t(key);
            if (attr) {
                el.setAttribute(attr, val);
            } else {
                el.textContent = val;
            }
        });
        // Update html lang attribute so the browser knows
        document.documentElement.lang = _currentLang;
    }

    window.i18n = {
        t:     _t,
        apply: _apply,
        lang:  function () { return _currentLang; },
    };

    // Aplica al cargar el DOM
    document.addEventListener('DOMContentLoaded', function () {
        var lang = document.documentElement.lang || localStorage.getItem('userLang') || 'es';
        _apply(lang);
    });
})();
