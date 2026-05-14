// Vista General Dashboard

const API = {
    cpu:          '/api/rendimiento/cpu',
    memory:       '/api/rendimiento/memory_detail',
    diskSummary:  '/api/rendimiento/disk_summary',
    systemInfo:   '/api/rendimiento/system_info',
    services:     '/api/rendimiento/services_status',
    security:     '/api/rendimiento/security_status',
    activity:     '/api/rendimiento/recent_activity',
    network:      '/api/rendimiento/network_stats',
};

// Lucide SVG snippets for dynamic rendering
const ICONS = {
    userRound: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/></svg>`,
    checkCircle2: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>`,
    triangleAlert: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
    shieldCheck: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/></svg>`,
    refreshCw: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>`,
    info: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>`,
    shieldCheckSm: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/></svg>`,
    triangleAlertSm: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
};

// --- Helpers ---

function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

function setHTML(id, html) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
}

function setBarWidth(id, pct) {
    const el = document.getElementById(id);
    if (el) el.style.width = Math.min(Math.max(pct, 0), 100) + '%';
}

function nowStr() {
    const d = new Date();
    const dd = String(d.getDate()).padStart(2,'0');
    const mm = String(d.getMonth()+1).padStart(2,'0');
    const yyyy = d.getFullYear();
    const hh = String(d.getHours()).padStart(2,'0');
    const mi = String(d.getMinutes()).padStart(2,'0');
    const ss = String(d.getSeconds()).padStart(2,'0');
    return `${dd}/${mm}/${yyyy} ${hh}:${mi}:${ss}`;
}

function mq(sep) {
    return window.MS ? window.MS.machineQuery(sep) : '';
}

async function safeFetch(url, signal) {
    try {
        const sep = url.includes('?') ? '&' : '?';
        const r = await fetch(url + mq(sep), { signal });
        if (!r.ok) throw new Error(r.status);
        return await r.json();
    } catch (e) {
        return null;
    }
}

// Pone el dashboard en estado "limpio" mientras llegan los nuevos datos.
function resetDashboard() {
    const dash = ['—', '—'];
    setText('cpuValue', '--%');           setText('cpuSub', 'Cargando…');
    setText('memValue', '-- GB');         setText('memSub', 'Cargando…');
    setText('diskValue', '-- GB');        setText('diskSub', 'Cargando…');
    setText('perfCpuPct', '--%');         setBarWidth('perfCpuBar', 0);
    setText('perfMemPct', '--%');         setBarWidth('perfMemBar', 0);
    setText('perfDiskPct', '--%');        setBarWidth('perfDiskBar', 0);
    setText('perfNetPct', '--%');         setBarWidth('perfNetBar', 0);
    setText('infoHostname', '—');
    setText('infoOS', '—');
    setText('infoLastBoot', '—');
    setText('infoIP', '—');
    setText('infoUser', '—');
    setText('infoUptime', '—');
}

// --- Update functions ---

function updateCPU(data) {
    if (!data) {
        setText('cpuValue', '—'); setText('cpuSub', 'Sin datos');
        setText('perfCpuPct', '—'); setBarWidth('perfCpuBar', 0);
        return;
    }
    const v = data.value ?? 0;
    const pct = Math.round(v);
    setText('cpuValue', pct + '%');
    const label = pct < 40 ? 'Carga media estable' : pct < 75 ? 'Carga moderada' : 'Carga alta';
    setText('cpuSub', label);
    setText('perfCpuPct', pct + '%');
    setBarWidth('perfCpuBar', pct);
}

function updateMemory(data) {
    if (!data) {
        setText('memValue', '—'); setText('memSub', 'Sin datos');
        setText('perfMemPct', '—'); setBarWidth('perfMemBar', 0);
        return;
    }
    const pct = Math.round(data.pct ?? data.value ?? 0);
    const usedGB = data.used_gb ?? 0;
    const totalGB = data.total_gb ?? 0;
    if (totalGB > 0) {
        setText('memValue', usedGB.toFixed(1) + ' / ' + totalGB.toFixed(0) + ' GB');
        setText('memSub', pct + '% en uso');
    } else {
        setText('memValue', pct + '%');
        setText('memSub', pct + '% en uso');
    }
    setText('perfMemPct', pct + '%');
    setBarWidth('perfMemBar', pct);
}

function updateDisk(data) {
    if (!data) {
        setText('diskValue', '—'); setText('diskSub', 'Sin datos');
        setText('perfDiskPct', '—'); setBarWidth('perfDiskBar', 0);
        return;
    }
    const freeGB = data.free_gb ?? 0;
    const totalGB = data.total_gb ?? 0;
    const usedPct = data.used_pct ?? 35;

    setText('diskValue', freeGB > 0 ? freeGB + ' GB' : Math.round(100 - usedPct) + '% libre');
    setText('diskSub', 'Espacio libre disponible');
    setText('perfDiskPct', Math.round(usedPct) + '%');
    setBarWidth('perfDiskBar', usedPct);

    const diskCard = document.getElementById('diskCard');
    if (usedPct > 90) diskCard && diskCard.classList.add('warn');
    else diskCard && diskCard.classList.remove('warn');
}

function updateSystemInfo(data) {
    if (!data) {
        ['infoHostname','infoOS','infoLastBoot','infoIP','infoUser','infoUptime',
         'sidebarHostname','sidebarOS','sidebarVersion'].forEach(id => setText(id, '—'));
        return;
    }
    const hostname = data.hostname || '-';
    const os = data.os || '-';
    const lastBoot = data.last_boot || '-';
    const uptime = data.uptime || '-';
    const ip = data.ip || '-';
    const user = data.user || '-';

    setText('infoHostname', hostname);
    setText('infoOS', os);
    setText('infoLastBoot', lastBoot);
    setText('infoIP', ip);
    setText('infoUser', user);
    setText('infoUptime', uptime);

    setText('sidebarHostname', hostname);
    setText('sidebarOS', os.length > 28 ? os.substring(0, 28) + '...' : os);
    setText('sidebarVersion', ip ? 'IP: ' + ip : '');
}

function updateServices(data) {
    if (!data || !data.services) return;
    const list = document.getElementById('servicesList');
    if (!list) return;

    let warnings = 0;
    list.innerHTML = data.services.map(s => {
        const st = s.status.toLowerCase();
        let badgeClass = 'desconocido';
        if (st === 'activo') badgeClass = 'activo';
        else if (st === 'inactivo') { badgeClass = 'inactivo'; warnings++; }
        else if (st.includes('pendiente')) { badgeClass = 'pendiente'; warnings++; }
        else if (st.includes('programado')) badgeClass = 'programado';
        else if (st.includes('no disponible')) { badgeClass = 'inactivo'; warnings++; }
        return `<div class="service-row">
            <span class="service-name">${s.name}</span>
            <span class="svc-badge ${badgeClass}">${s.status}</span>
        </div>`;
    }).join('');

    updateStatusCard(warnings);
}

function updateStatusCard(warnings) {
    const card = document.getElementById('statusCard');
    if (!card) return;

    const iconWrap = document.getElementById('statusIconWrap');
    const shieldCheckSvg = `<svg id="statusIcon" xmlns="http://www.w3.org/2000/svg" width="46" height="46" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/></svg>`;
    const triangleSvg = `<svg id="statusIcon" xmlns="http://www.w3.org/2000/svg" width="46" height="46" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`;

    if (warnings === 0) {
        card.className = 'stat-card status';
        if (iconWrap) iconWrap.innerHTML = shieldCheckSvg;
        setText('statusValue', 'OK');
        setText('statusSub', 'Sistema en buen estado');
    } else {
        card.className = 'stat-card status warn';
        if (iconWrap) iconWrap.innerHTML = triangleSvg;
        setText('statusValue', warnings === 1 ? '1 alerta' : warnings + ' alertas');
        setText('statusSub', warnings + (warnings === 1 ? ' advertencia menor' : ' advertencias menores'));
    }
}

function updateNetwork(data) {
    if (!data) return;
    const pct = data.usage_pct ?? 0;
    setText('perfNetPct', Math.round(pct) + '%');
    setBarWidth('perfNetBar', pct);
}

function updateActivity(data) {
    if (!data || !data.events) return;
    const list = document.getElementById('activityList');
    if (!list) return;

    if (data.events.length === 0) {
        list.innerHTML = '<div class="text-muted">No hay eventos recientes</div>';
        return;
    }

    // Map event type to icon and color
    const iconMap = {
        'error':   { svg: ICONS.triangleAlert, color: '#D89A13' },
        'warning': { svg: ICONS.triangleAlert, color: '#D89A13' },
        'info':    { svg: ICONS.checkCircle2,  color: '#2EA043' },
        'login':   { svg: ICONS.userRound,     color: '#2EA043' },
        'backup':  { svg: ICONS.shieldCheck,   color: '#0A67DC' },
        'reboot':  { svg: ICONS.refreshCw,     color: '#0A67DC' },
    };

    list.innerHTML = data.events.slice(0, 5).map(e => {
        const ic = iconMap[e.type] || { svg: ICONS.info, color: '#0A67DC' };
        const svgStyled = ic.svg.replace('stroke="currentColor"', `stroke="${ic.color}"`);
        const timeStr = e.time || '';
        const msg = `${e.source ? e.source + ': ' : ''}${e.message}`;
        return `<div class="activity-item">
            <span class="act-time">${timeStr}</span>
            <span class="act-icon-svg">${svgStyled}</span>
            <span class="act-msg">${msg}</span>
        </div>`;
    }).join('');
}

function updateSecurity(data) {
    const alertsList = document.getElementById('alertsList');
    const secStatus = document.getElementById('securityStatus');
    if (!alertsList || !secStatus) return;

    if (!data) {
        alertsList.innerHTML = '<div class="text-muted">No se pudo cargar estado de seguridad</div>';
        return;
    }

    const alerts = [];
    const wuStatus = data.windows_update || '';
    if (wuStatus && wuStatus.toLowerCase().includes('activo')) {
        alerts.push({ type: 'warning', text: 'Windows Update activo. Verifique si hay actualizaciones pendientes.' });
    }

    const avStatus = data.antivirus || '';
    const fwStatus = data.firewall || '';

    if (!avStatus || avStatus.toLowerCase().includes('desconocido')) {
        alerts.push({ type: 'warning', text: 'No se pudo verificar el estado del antivirus.' });
    }
    if (!fwStatus || fwStatus.toLowerCase().includes('deshabilitado')) {
        alerts.push({ type: 'error', text: 'Firewall deshabilitado. Se recomienda activarlo.' });
    }

    if (alerts.length === 0) {
        alerts.push({ type: 'ok', text: 'No se detectaron alertas de seguridad.' });
    }

    const triangleIconColored = ICONS.triangleAlertSm.replace('stroke="currentColor"', 'stroke="#D89A13"');

    alertsList.innerHTML = alerts.map((a, i) => {
        const iconHtml = (a.type === 'warning' || a.type === 'error')
            ? `<span class="alert-icon">${triangleIconColored}</span>`
            : `<span class="alert-info-badge">i</span>`;
        return `<div class="alert-item">
            ${iconHtml}
            <span class="alert-text">${a.text}</span>
        </div>`;
    }).join('');

    const avOk = avStatus && !avStatus.toLowerCase().includes('desconocido') && !avStatus.toLowerCase().includes('inactiva');
    const fwOk = fwStatus && fwStatus.toLowerCase().includes('habilitado');

    const shieldSvgGreen = ICONS.shieldCheckSm.replace('stroke="currentColor"', 'stroke="#249B35"');

    secStatus.innerHTML = `
        <div class="sec-row">
            <span class="sec-label">${shieldSvgGreen} Antivirus</span>
            <span class="sec-value ${avOk ? '' : 'bad'}">${avStatus || 'Desconocido'}</span>
        </div>
        <div class="sec-row">
            <span class="sec-label">${shieldSvgGreen} Firewall</span>
            <span class="sec-value ${fwOk ? '' : 'bad'}">${fwStatus || 'Desconocido'}</span>
        </div>`;
}

// --- Connection indicator ---
// Arranca en 0 → estado "desconectado" hasta que llegue una respuesta válida
let lastSuccessfulFetch = 0;

function checkConnection() {
    const dotSvg = document.getElementById('connDotSvg');
    const label = document.getElementById('connLabel');
    if (!dotSvg || !label) return;
    const ok = (Date.now() - lastSuccessfulFetch) < 30000;
    if (ok) {
        dotSvg.setAttribute('fill', '#38B000');
        dotSvg.setAttribute('stroke', '#38B000');
        label.textContent = 'CONECTADO';
    } else {
        dotSvg.setAttribute('fill', '#ef4444');
        dotSvg.setAttribute('stroke', '#ef4444');
        label.textContent = 'SIN CONEXIÓN';
    }
}

// --- Main refresh ---
// Si el usuario cambia rápido entre máquinas, abortamos el refresh anterior
// para que su respuesta lenta (10s timeout en máquinas offline) no sobrescriba
// los datos de la máquina actual.
let _refreshCtrl = null;

async function refreshAll(opts) {
    const btn = document.getElementById('refreshBtn');
    if (btn) btn.classList.add('loading');

    // Cancelar refresh anterior si sigue en vuelo
    if (_refreshCtrl) {
        try { _refreshCtrl.abort(); } catch (_) {}
    }
    const ctrl = new AbortController();
    _refreshCtrl = ctrl;

    // En refresh COMPLETO (cambio de máquina o carga inicial) limpiamos UI
    // para que no se vea info de la máquina anterior. En refresh "ligero"
    // (auto-refresh de perf) NO limpiamos para evitar flicker.
    if (!opts || opts.partial !== true) {
        resetDashboard();
    }

    const [cpu, mem, disk, sysInfo, svc, sec, act, net] = await Promise.all([
        safeFetch(API.cpu,         ctrl.signal),
        safeFetch(API.memory,      ctrl.signal),
        safeFetch(API.diskSummary, ctrl.signal),
        safeFetch(API.systemInfo,  ctrl.signal),
        safeFetch(API.services,    ctrl.signal),
        safeFetch(API.security,    ctrl.signal),
        safeFetch(API.activity,    ctrl.signal),
        safeFetch(API.network,     ctrl.signal),
    ]);

    // Si nos abortaron mientras tanto, NO actualizamos UI (otro refresh ya está)
    if (ctrl.signal.aborted) return;

    if ((cpu && cpu.reachable === true) || (mem && mem.reachable === true)) {
        lastSuccessfulFetch = Date.now();
    }

    updateCPU(cpu);
    updateMemory(mem);
    updateDisk(disk);
    updateSystemInfo(sysInfo);
    updateServices(svc);
    updateSecurity(sec);
    updateActivity(act);
    updateNetwork(net);
    checkConnection();

    setText('lastUpdate', nowStr());
    if (btn) btn.classList.remove('loading');
}

// --- Sidebar toggle ---
(function () {
    const sidebar = document.getElementById('sidebar');
    if (localStorage.getItem('sidebarCollapsed') === 'true') {
        sidebar?.classList.add('collapsed');
    }
    document.getElementById('sidebarToggle')?.addEventListener('click', () => {
        sidebar?.classList.toggle('collapsed');
        localStorage.setItem('sidebarCollapsed', sidebar?.classList.contains('collapsed') ? 'true' : 'false');
    });
})();

// --- Refresh button ---
document.getElementById('refreshBtn')?.addEventListener('click', refreshAll);

// --- Actualizar quick action ---
document.getElementById('btnActualizar')?.addEventListener('click', refreshAll);

// --- Init ---
refreshAll();

// Recargar todo al cambiar máquina
window.addEventListener('machineChanged', refreshAll);

// Auto-refresh every 15 seconds for perf data
async function refreshPerf() {
    const [cpu, mem, net] = await Promise.all([
        safeFetch(API.cpu),
        safeFetch(API.memory),
        safeFetch(API.network),
    ]);
    // Sólo se considera conectado si el endpoint marca explícitamente reachable=true
    // (cuando la máquina remota no responde, el backend devuelve 0s pero reachable=false)
    if ((cpu && cpu.reachable === true) || (mem && mem.reachable === true)) {
        lastSuccessfulFetch = Date.now();
    }
    updateCPU(cpu);
    updateMemory(mem);
    updateNetwork(net);
    checkConnection();
    setText('lastUpdate', nowStr());
}
setInterval(refreshPerf, 15000);

// Full refresh every 60 seconds
setInterval(refreshAll, 60000);
