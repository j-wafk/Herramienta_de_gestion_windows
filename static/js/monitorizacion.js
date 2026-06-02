// static/js/monitorizacion.js
// Página de Monitorización: máquinas + servicios TCP/UDP + actividad reciente.

document.addEventListener('DOMContentLoaded', function () {

    // ── DOM ──────────────────────────────────────────────────────────
    const elSvcUp     = document.getElementById('mSvcUp');
    const elSvcTotal  = document.getElementById('mSvcTotal');
    const elMachOn    = document.getElementById('mMachOnline');
    const elMachTotal = document.getElementById('mMachTotal');
    const elMachBody  = document.getElementById('machBody');
    const elSvcBody   = document.getElementById('svcBody');
    const elActBody   = document.getElementById('actBody');
    const machSearch  = document.getElementById('machSearch');

    const btnAddMachine = document.getElementById('btnAddMachine');
    const btnAddService = document.getElementById('btnAddService');
    const btnEditService= document.getElementById('btnEditService');
    const refreshBtn    = document.getElementById('refreshBtn');

    const machineModal  = document.getElementById('machineModal');
    const serviceModal  = document.getElementById('serviceModal');

    const userRole = document.body.dataset.userRole || 'solo_lectura';
    // operador puede CRUD máquinas (admin/superadmin también);
    // servicios monitorizados quedan reservados a admin/superadmin.
    const canWrite        = ['superadmin', 'admin', 'operador'].includes(userRole);
    const canWriteServices= ['superadmin', 'admin'].includes(userRole);

    // ── Estado ───────────────────────────────────────────────────────
    let machines = [];
    let services = [];
    let activity = [];
    let editingMachineId = null;
    let editingServiceId = null;
    let selectedServiceId = null;
    let _initialPingDone = false;  // sondea todas al entrar; refresh siguientes usan GET

    // ── Helpers ──────────────────────────────────────────────────────
    function escapeHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }
    function fmtDate(s) {
        if (!s) return '—';
        const d = new Date(s);
        if (isNaN(d.getTime())) return s;
        return d.toLocaleString('es-ES', {
            day: '2-digit', month: '2-digit', year: 'numeric',
            hour: '2-digit', minute: '2-digit', second: '2-digit',
        });
    }
    function setLastUpdate() {
        const el = document.getElementById('lastUpdate');
        if (el) el.textContent = new Date().toLocaleString('es-ES');
    }

    async function api(method, path, body) {
        const opts = {
            method,
            credentials: 'same-origin',
            headers: { 'Accept': 'application/json' },
        };
        if (body !== undefined && method !== 'GET') {
            opts.headers['Content-Type'] = 'application/json';
            opts.body = JSON.stringify(body);
        }
        const r = await fetch(path, opts);
        const ct = r.headers.get('content-type') || '';
        let data = null;
        if (ct.includes('application/json')) {
            try { data = await r.json(); } catch (_) {}
        }
        if (!r.ok) {
            const msg = (data && data.error) || `HTTP ${r.status}`;
            const err = new Error(msg);
            err.status = r.status;
            throw err;
        }
        // Si el servidor respondió 200 pero no es JSON (p.ej. página de login HTML),
        // lo tratamos como sesión expirada para no fallar en silencio.
        if (!ct.includes('application/json')) {
            const err = new Error('Respuesta no JSON (¿sesión caducada?)');
            err.status = 0;
            throw err;
        }
        return data;
    }

    // ── Mapeo de iconos por nombre ───────────────────────────────────
    function iconKey(svc) {
        if (svc.icon_key) return svc.icon_key;
        const n = (svc.name || '').toLowerCase();
        if (n.includes('winrm'))   return 'winrm';
        if (n.includes('iis') || n.includes('web')) return 'iis';
        if (n.includes('sql'))     return 'sql';
        if (n.includes('rdp'))     return 'rdp';
        if (n.includes('dns'))     return 'dns';
        if (n.includes('backup'))  return 'backup';
        if (n.includes('ssh'))     return 'ssh';
        if (n.includes('http') || n.includes('api')) return 'api';
        return '';
    }
    function iconLabel(svc) {
        const key = iconKey(svc);
        if (key) return key.toUpperCase().slice(0, 3);
        const w = (svc.name || '').trim().split(/\s+/)[0] || '?';
        return w.slice(0, 3).toUpperCase();
    }

    // ── Estados de display ───────────────────────────────────────────
    function machineStatus(m) {
        const s = (m && m.status || 'unknown').toLowerCase();
        if (s === 'online')  return ['online',  'Activa'];
        if (s === 'offline') return ['offline', 'Desconectada'];
        if (s === 'warning') return ['warning', 'Advertencia'];
        return ['unknown', 'Desconocida'];
    }
    function serviceStatus(s) {
        const st = (s.last_status || 'unknown').toLowerCase();
        if (st === 'up')      return ['up',      'Funcionando'];
        if (st === 'down')    return ['down',    'Caído'];
        if (st === 'warning') return ['warning', 'Advertencia'];
        return ['unknown', 'Sin datos'];
    }

    // ── Render ───────────────────────────────────────────────────────
    function renderSummary(s) {
        if (elSvcUp)     elSvcUp.textContent     = s.services_up ?? 0;
        if (elSvcTotal)  elSvcTotal.textContent  = s.services_total ?? 0;
        if (elMachOn)    elMachOn.textContent    = s.machines_online ?? 0;
        if (elMachTotal) elMachTotal.textContent = s.machines_total ?? 0;
    }

    function renderMachines(errMsg) {
        if (!elMachBody) return;
        if (errMsg) {
            elMachBody.innerHTML = `<tr><td colspan="5" class="mon-empty" style="color:#dc2626">Error cargando máquinas: ${escapeHtml(errMsg)}</td></tr>`;
            return;
        }
        const q = (machSearch?.value || '').trim().toLowerCase();
        const list = (machines || []).filter(m =>
            !q || (m.name || '').toLowerCase().includes(q)
               || (m.ip || '').toLowerCase().includes(q)
               || (m.description || '').toLowerCase().includes(q)
        );
        if (list.length === 0) {
            const total = (machines || []).length;
            const msg = total === 0
                ? 'No hay máquinas registradas. Añade una desde el selector superior o el botón "+ Añadir máquina".'
                : `Ninguna máquina coincide con "${q}".`;
            elMachBody.innerHTML = `<tr><td colspan="5" class="mon-empty">${escapeHtml(msg)}</td></tr>`;
            return;
        }
        const html = list.map(m => {
            const [cls, label] = machineStatus(m);
            const name = escapeHtml(m.name || '—');
            const ip   = escapeHtml(m.ip   || '—');
            const desc = escapeHtml(m.description || '');
            const editBtn = canWrite
                ? `<button class="mon-btn secondary" data-mach-edit="${m.id}" style="padding:4px 10px;font-size:12px">Editar</button>`
                : '';
            return `<tr>` +
                `<td><strong>${name}</strong></td>` +
                `<td><code class="mon-ip-code">${ip}</code></td>` +
                `<td><span class="mon-status ${cls}"><span class="dot"></span><span class="badge">${label}</span></span></td>` +
                `<td class="mon-desc">${desc ? desc : '<span class="mon-empty-cell">—</span>'}</td>` +
                (canWrite ? `<td style="text-align:right">${editBtn}</td>` : '') +
                `</tr>`;
        }).join('');
        console.log('[monit] renderMachines: inserting', list.length, 'rows. HTML length:', html.length);
        elMachBody.innerHTML = html;
    }

    function renderServices() {
        if (!elSvcBody) return;
        if (services.length === 0) {
            elSvcBody.innerHTML = `<tr><td colspan="7" class="mon-empty">No hay servicios monitorizados. Pulsa "Añadir servicio".</td></tr>`;
            return;
        }
        elSvcBody.innerHTML = services.map(s => {
            const [cls, label] = serviceStatus(s);
            const ic = iconKey(s);
            const sel = s.id === selectedServiceId ? ' class="selected"' : '';
            return `
                <tr data-svc-id="${s.id}"${sel}>
                    <td>${escapeHtml(s.machine_name || '—')}</td>
                    <td>
                        <span class="svc-icon ${escapeHtml(ic)}">${escapeHtml(iconLabel(s))}</span>
                        ${escapeHtml(s.name)}
                    </td>
                    <td><code>${escapeHtml(s.ip)}</code></td>
                    <td>${s.port}</td>
                    <td>${escapeHtml(s.protocol || 'TCP')}</td>
                    <td><span class="mon-status ${cls}"><span class="dot"></span><span class="badge">${label}</span></span></td>
                    <td>${fmtDate(s.last_check)}</td>
                </tr>`;
        }).join('');
    }

    function renderActivity() {
        if (!elActBody) return;
        if (activity.length === 0) {
            elActBody.innerHTML = `<tr><td colspan="5" class="mon-empty">Sin eventos recientes.</td></tr>`;
            return;
        }
        elActBody.innerHTML = activity.map(e => {
            const cls = e.status === 'up' ? 'up' :
                        e.status === 'warning' ? 'warning' :
                        e.status === 'down' ? 'down' : 'unknown';
            const label = e.status === 'up' ? 'OK' :
                          e.status === 'warning' ? 'Advertencia' :
                          e.status === 'down' ? 'Error' : '—';
            return `
                <tr>
                    <td>${fmtDate(e.timestamp)}</td>
                    <td>${escapeHtml(e.machine_name || '—')}</td>
                    <td>
                        <span class="svc-icon ${escapeHtml(e.icon_key || '')}">${escapeHtml((e.icon_key || (e.service_name || '?')).toUpperCase().slice(0,3))}</span>
                        ${escapeHtml(e.service_name || '—')}
                    </td>
                    <td>${escapeHtml(e.message || '—')}</td>
                    <td><span class="mon-status ${cls}"><span class="dot"></span>${label}</span></td>
                </tr>`;
        }).join('');
    }

    // ── Carga ────────────────────────────────────────────────────────
    // GET inmediato (la tabla SIEMPRE se rellena). En la primera carga marca
    // cada máquina como _checking y dispara un ping individual por cada una;
    // cada respuesta actualiza SOLO esa fila → la tabla "se ilumina" sola a
    // medida que llegan resultados, sin bloquear nada.
    async function loadMachines() {
        console.log('[monit] loadMachines: start (initialPingDone=%s)', _initialPingDone);
        try {
            const resp = await api('GET', '/api/machines');
            machines = Array.isArray(resp) ? resp : (resp && resp.machines) || [];
            console.log('[monit] loadMachines: %d items', machines.length);
        } catch (e) {
            console.error('[monit] loadMachines FAIL', e);
            machines = [];
            renderMachines(e.message || 'fallo de red');
            return;
        }

        renderMachines();
        // En la PRIMERA carga: pingea cada máquina en paralelo. Cada respuesta
        // actualiza solo SU fila (sin badge "Comprobando…", la fila simplemente
        // muta su estado cuando llega el resultado). Auto-refresh posteriores
        // (cada 15 s + machineChanged + tras CRUD) usan solo el GET.
        if (!_initialPingDone) {
            _initialPingDone = true;
            machines.forEach(m => pingSingleMachine(m.id));
        }
    }

    // Ping individual fire-and-forget. Actualiza el estado de UNA máquina en
    // cuanto llega su respuesta; no bloquea ni espera al resto.
    function pingSingleMachine(id) {
        api('POST', `/api/machines/${id}/ping`)
            .then(r => {
                const newStatus = (r && r.status) || 'offline';
                applyPingResult(id, newStatus);
            })
            .catch(err => {
                applyPingResult(id, 'offline');
                console.warn('[monit] ping id=%s falló:', id, err && err.message);
            });
    }

    function applyPingResult(id, newStatus) {
        const m = machines.find(x => x.id === id);
        if (m && m.status !== newStatus) {
            m.status = newStatus;
            renderMachines();
        }
        // Sincroniza el dropdown superior y el badge "CONECTADO/DESCONECTADO"
        // del header — sin esto, el header se queda hardcodeado en verde.
        if (window.MS && typeof window.MS.setMachineStatus === 'function') {
            window.MS.setMachineStatus(id, newStatus);
        }
    }
    async function loadServices() {
        try {
            const resp = await api('GET', '/api/monitorizacion/services');
            services = (resp && resp.services) || [];
            renderServices();
            updateEditButton();
        } catch (e) {
            console.error('loadServices', e);
            services = [];
            if (elSvcBody) elSvcBody.innerHTML = `<tr><td colspan="7" class="mon-empty" style="color:#dc2626">Error cargando servicios: ${escapeHtml(e.message || '')}</td></tr>`;
        }
    }
    async function loadActivity() {
        try {
            const resp = await api('GET', '/api/monitorizacion/activity?limit=15');
            activity = (resp && resp.events) || [];
            renderActivity();
        } catch (e) {
            console.error('loadActivity', e);
            activity = [];
            if (elActBody) elActBody.innerHTML = `<tr><td colspan="5" class="mon-empty" style="color:#dc2626">Error cargando actividad: ${escapeHtml(e.message || '')}</td></tr>`;
        }
    }
    async function loadSummary() {
        try {
            const s = await api('GET', '/api/monitorizacion/summary');
            renderSummary(s || {});
        } catch (e) {
            console.error('loadSummary', e);
            renderSummary({});
        }
    }

    async function loadAll() {
        console.log('[monit] loadAll: kick off');
        // Lanzar en paralelo, pero cada uno con su propio try/catch.
        await Promise.all([loadSummary(), loadMachines(), loadServices(), loadActivity()]);
        setLastUpdate();
    }

    function updateEditButton() {
        if (btnEditService) btnEditService.disabled = !selectedServiceId;
    }

    // ── Modal Máquina ────────────────────────────────────────────────
    function openMachineModal(m) {
        editingMachineId = m ? m.id : null;
        document.getElementById('machineModalTitle').textContent = m ? 'Editar máquina' : 'Añadir máquina';
        document.getElementById('mMachineName').value = m ? m.name : '';
        document.getElementById('mMachineIp').value   = m ? m.ip : '';
        document.getElementById('mMachinePort').value = m ? m.port : 12345;
        document.getElementById('mMachineDesc').value = m ? (m.description || '') : '';
        const delBtn = document.getElementById('deleteMachine');
        if (delBtn) delBtn.style.display = m ? 'inline-flex' : 'none';
        machineModal.classList.add('open');
    }
    function closeMachineModal() { machineModal.classList.remove('open'); }

    async function saveMachine() {
        const payload = {
            name:        document.getElementById('mMachineName').value.trim(),
            ip:          document.getElementById('mMachineIp').value.trim(),
            port:        parseInt(document.getElementById('mMachinePort').value, 10) || 12345,
            description: document.getElementById('mMachineDesc').value.trim(),
        };
        if (!payload.name || !payload.ip) { alert('Nombre e IP obligatorios.'); return; }
        try {
            if (editingMachineId) {
                await api('PUT',  `/api/monitorizacion/machines/${editingMachineId}`, payload);
            } else {
                await api('POST', `/api/monitorizacion/machines`, payload);
            }
            closeMachineModal();
            await loadAll();
            if (window.MS && typeof window.MS.reload === 'function') window.MS.reload();
        } catch (e) {
            alert('Error: ' + e.message);
        }
    }

    async function deleteMachine() {
        if (!editingMachineId) return;
        if (!confirm('¿Eliminar esta máquina? Los servicios asociados quedarán huérfanos.')) return;
        try {
            await api('DELETE', `/api/monitorizacion/machines/${editingMachineId}`);
            closeMachineModal();
            await loadAll();
            if (window.MS && typeof window.MS.reload === 'function') window.MS.reload();
        } catch (e) {
            alert('Error: ' + e.message);
        }
    }

    // ── Modal Servicio ───────────────────────────────────────────────
    function fillMachineSelect(currentId) {
        const sel = document.getElementById('mSvcMachine');
        if (!sel) return;
        sel.innerHTML = '<option value="">— Sin máquina (servicio externo) —</option>' +
            machines.map(m => `<option value="${m.id}">${escapeHtml(m.name)} (${escapeHtml(m.ip)})</option>`).join('');
        if (currentId) sel.value = String(currentId);
    }

    function openServiceModal(svc) {
        editingServiceId = svc ? svc.id : null;
        document.getElementById('serviceModalTitle').textContent = svc ? 'Editar servicio' : 'Añadir servicio';
        fillMachineSelect(svc ? svc.machine_id : null);
        document.getElementById('mSvcName').value     = svc ? svc.name : '';
        document.getElementById('mSvcIp').value       = svc ? svc.ip : '';
        document.getElementById('mSvcPort').value     = svc ? svc.port : '';
        document.getElementById('mSvcProto').value    = svc ? (svc.protocol || 'TCP') : 'TCP';
        document.getElementById('mSvcEnabled').value  = svc && !svc.enabled ? '0' : '1';
        const delBtn = document.getElementById('deleteService');
        if (delBtn) delBtn.style.display = svc ? 'inline-flex' : 'none';
        serviceModal.classList.add('open');
    }
    function closeServiceModal() { serviceModal.classList.remove('open'); }

    async function saveService() {
        const machineSel = document.getElementById('mSvcMachine').value;
        const payload = {
            machine_id: machineSel ? parseInt(machineSel, 10) : null,
            name:       document.getElementById('mSvcName').value.trim(),
            ip:         document.getElementById('mSvcIp').value.trim(),
            port:       parseInt(document.getElementById('mSvcPort').value, 10),
            protocol:   document.getElementById('mSvcProto').value,
            enabled:    document.getElementById('mSvcEnabled').value === '1',
        };
        if (!payload.name || !payload.ip || !payload.port) {
            alert('Nombre, IP y puerto son obligatorios.'); return;
        }
        try {
            if (editingServiceId) {
                await api('PUT',  `/api/monitorizacion/services/${editingServiceId}`, payload);
            } else {
                await api('POST', `/api/monitorizacion/services`, payload);
            }
            closeServiceModal();
            await loadAll();
        } catch (e) {
            alert('Error: ' + e.message);
        }
    }

    async function deleteService() {
        if (!editingServiceId) return;
        if (!confirm('¿Eliminar este servicio monitorizado?')) return;
        try {
            await api('DELETE', `/api/monitorizacion/services/${editingServiceId}`);
            selectedServiceId = null;
            closeServiceModal();
            await loadAll();
        } catch (e) {
            alert('Error: ' + e.message);
        }
    }

    // ── Listeners ────────────────────────────────────────────────────
    if (btnAddMachine) btnAddMachine.addEventListener('click', () => openMachineModal(null));
    if (btnAddService) btnAddService.addEventListener('click', () => openServiceModal(null));
    if (btnEditService) btnEditService.addEventListener('click', () => {
        const svc = services.find(s => s.id === selectedServiceId);
        if (svc) openServiceModal(svc);
    });
    if (refreshBtn) refreshBtn.addEventListener('click', loadAll);

    document.getElementById('saveMachine')?.addEventListener('click', saveMachine);
    document.getElementById('cancelMachine')?.addEventListener('click', closeMachineModal);
    document.getElementById('closeMachineModal')?.addEventListener('click', closeMachineModal);
    document.getElementById('deleteMachine')?.addEventListener('click', deleteMachine);

    document.getElementById('saveService')?.addEventListener('click', saveService);
    document.getElementById('cancelService')?.addEventListener('click', closeServiceModal);
    document.getElementById('closeServiceModal')?.addEventListener('click', closeServiceModal);
    document.getElementById('deleteService')?.addEventListener('click', deleteService);

    // Click delegado: editar máquina
    if (elMachBody) elMachBody.addEventListener('click', (ev) => {
        const btn = ev.target.closest('[data-mach-edit]');
        if (!btn) return;
        const m = machines.find(x => x.id === parseInt(btn.dataset.machEdit, 10));
        if (m) openMachineModal(m);
    });

    // Click delegado: seleccionar servicio (para botón Editar)
    if (elSvcBody) elSvcBody.addEventListener('click', (ev) => {
        const tr = ev.target.closest('tr[data-svc-id]');
        if (!tr) return;
        const id = parseInt(tr.dataset.svcId, 10);
        selectedServiceId = (selectedServiceId === id) ? null : id;
        renderServices();
        updateEditButton();
    });
    // Doble click → editar directamente
    if (elSvcBody) elSvcBody.addEventListener('dblclick', (ev) => {
        const tr = ev.target.closest('tr[data-svc-id]');
        if (!tr) return;
        const id = parseInt(tr.dataset.svcId, 10);
        const svc = services.find(s => s.id === id);
        if (svc) openServiceModal(svc);
    });

    // Wrap en arrow para que el InputEvent no llegue como errMsg de renderMachines
    if (machSearch) machSearch.addEventListener('input', () => renderMachines());

    // Sincronización con el selector superior: si el usuario añade/elimina máquinas allí,
    // recargamos esta página para reflejar la misma lista.
    window.addEventListener('machineListChanged', loadAll);
    window.addEventListener('machineChanged',     loadAll);

    // Auto-refresh cada 15 s
    setInterval(() => {
        if (document.visibilityState === 'visible') loadAll();
    }, 15000);

    loadAll();
});
