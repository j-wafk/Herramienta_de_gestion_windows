// static/js/backup.js
// Gestión de copias de seguridad: trabajos, destinos, historial.
// Todas las acciones consumen los endpoints de /api/backup/*.

document.addEventListener('DOMContentLoaded', function () {
    // ── DOM refs ─────────────────────────────────────────────────────
    const statusIndicator   = document.getElementById('status-indicator');
    const jobsList          = document.getElementById('jobsList');
    const destinationsList  = document.getElementById('destinationsList');
    const historyTableBody  = document.getElementById('historyTableBody');

    const backupJobModal    = document.getElementById('backupJobModal');
    const destinationModal  = document.getElementById('destinationModal');
    const backupDetailsModal= document.getElementById('backupDetailsModal');
    const commandModal      = document.getElementById('commandModal');

    const createBackupJobBtn = document.getElementById('createBackupJobBtn');
    const addDestinationBtn  = document.getElementById('addDestinationBtn');
    const refreshHistoryBtn  = document.getElementById('refreshHistoryBtn');

    const progressPanel      = document.getElementById('progressPanel');
    const progressFill       = document.getElementById('progressFill');
    const progressText       = document.getElementById('progressText');
    const progressDetails    = document.getElementById('progressDetails');
    const progressFiles      = document.getElementById('progressFiles');
    const progressSize       = document.getElementById('progressSize');
    const progressTime       = document.getElementById('progressTime');
    const closeProgressBtn   = document.getElementById('closeProgressBtn');

    // ── Estado ───────────────────────────────────────────────────────
    let destinations = [];
    let jobs         = [];
    let editingJobId = null;
    let editingDestId = null;
    let currentRunId = null;
    let pollTimer    = null;

    // Historial paginado
    const HISTORY_PAGE_SIZE = 20;
    const HISTORY_PREFETCH  = 2;  // pre-cargar las 2 páginas siguientes
    const historyCache = new Map();   // key: `${q}|${page}` -> array
    let historyTotal   = 0;
    let historyPage    = 1;
    let historyQuery   = '';
    let historySearchTimer = null;

    const userRole = document.body.dataset.userRole || 'solo_lectura';
    const canWrite = ['superadmin', 'admin'].includes(userRole);

    // ── Helpers ──────────────────────────────────────────────────────
    function mid() {
        return (window.MS && window.MS.getMachineId && window.MS.getMachineId()) || null;
    }

    function withMachine(path) {
        const m = mid();
        if (!m) return path;
        return path + (path.includes('?') ? '&' : '?') + 'machine_id=' + encodeURIComponent(m);
    }

    async function api(method, path, body) {
        const opts = { method, headers: { 'Accept': 'application/json' } };
        if (body !== undefined && method !== 'GET') {
            opts.headers['Content-Type'] = 'application/json';
            opts.body = JSON.stringify(Object.assign({}, body, mid() ? { machine_id: mid() } : {}));
        }
        // Siempre añadir machine_id a la URL para que el audit log resuelva
        // bien la máquina aunque el endpoint no lleve body.
        const url = withMachine(path);
        const res = await fetch(url, opts);
        let data = null;
        try { data = await res.json(); } catch (_) {}
        if (!res.ok) {
            const msg = (data && data.error) || (`HTTP ${res.status}`);
            const err = new Error(msg);
            err.status = res.status;
            err.data = data;
            throw err;
        }
        return data;
    }

    function fmtBytes(n) {
        n = Number(n) || 0;
        if (n >= 1024 ** 3) return (n / 1024 ** 3).toFixed(2) + ' GB';
        if (n >= 1024 ** 2) return (n / 1024 ** 2).toFixed(1) + ' MB';
        if (n >= 1024)      return (n / 1024).toFixed(0) + ' KB';
        return n + ' B';
    }

    function fmtDate(s) {
        if (!s) return '—';
        const d = new Date(s);
        if (isNaN(d.getTime())) return s;
        return d.toLocaleString('es-ES', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
    }

    function fmtDuration(sec) {
        sec = Number(sec) || 0;
        const m = Math.floor(sec / 60);
        const s = Math.floor(sec % 60);
        return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
    }

    function escapeHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function backupTypeLabel(t) {
        return ({ full: 'Completo', incremental: 'Incremental', differential: 'Diferencial' })[t] || t || '—';
    }

    function scheduleLabel(s, time) {
        if (s === 'manual') return 'Manual';
        if (s === 'daily')  return 'Diario a las ' + time;
        if (s === 'weekly') return 'Semanal a las ' + time;
        if (s === 'monthly')return 'Mensual a las ' + time;
        return s || '—';
    }

    function destTypeLabel(t) {
        return ({ local: 'Local', network: 'Red', cloud: 'Nube', ftp: 'FTP' })[t] || t || '—';
    }

    function updateStatus(state) {
        if (!statusIndicator) return;
        statusIndicator.className = 'status';
        const map = {
            connected:   ['connected',   'CONECTADO'],
            loading:     ['loading',     'CARGANDO...'],
            error:       ['disconnected','ERROR DE CONEXIÓN'],
            disconnected:['disconnected','DESCONECTADO'],
        };
        const [cls, txt] = map[state] || map.disconnected;
        statusIndicator.classList.add(cls);
        statusIndicator.textContent = txt;
    }

    function toast(msg, isError) {
        // Simple toast con commandModal reutilizado, sin shell input.
        const title = document.getElementById('commandModalTitle');
        const out   = document.getElementById('commandOutput');
        if (title) title.textContent = isError ? 'Error' : 'Información';
        if (out) {
            out.textContent = msg;
            out.style.color = isError ? '#dc2626' : '';
        }
        if (commandModal) commandModal.style.display = 'block';
    }

    // ── Carga inicial y refrescos ────────────────────────────────────
    async function loadAll() {
        updateStatus('loading');
        try {
            const [destResp, jobResp, sumResp] = await Promise.all([
                api('GET', '/api/backup/destinations'),
                api('GET', '/api/backup/jobs'),
                api('GET', '/api/backup/summary'),
            ]);
            destinations = destResp.destinations || [];
            jobs         = jobResp.jobs || [];
            renderDestinations();
            renderJobs();
            renderSummary(sumResp);
            updateStatus('connected');
        } catch (e) {
            console.error('loadAll error', e);
            updateStatus('error');
            renderEmpty();
            toast('No se pudieron cargar los datos: ' + e.message, true);
            refreshSummary();
        }
        // Historial se gestiona aparte (paginado + cache)
        await reloadHistory();
    }

    function invalidateHistoryCache() {
        historyCache.clear();
    }

    async function reloadHistory() {
        invalidateHistoryCache();
        historyPage = 1;
        await loadHistoryPage(1);
    }

    function cacheKey(q, page) { return q + '|' + page; }

    async function fetchHistoryPage(page, useQuery) {
        const q = (useQuery !== undefined) ? useQuery : historyQuery;
        const key = cacheKey(q, page);
        if (historyCache.has(key)) return historyCache.get(key);
        const offset = (page - 1) * HISTORY_PAGE_SIZE;
        const params = new URLSearchParams({
            limit:  HISTORY_PAGE_SIZE,
            offset: offset,
        });
        if (q) params.set('q', q);
        const resp = await api('GET', '/api/backup/history?' + params.toString());
        const rows = resp.history || [];
        historyCache.set(key, rows);
        if (typeof resp.total === 'number') historyTotal = resp.total;
        return rows;
    }

    async function loadHistoryPage(page) {
        try {
            const rows = await fetchHistoryPage(page);
            historyPage = page;
            renderHistoryPage(rows);
            renderHistoryPagination();
            // Pre-fetch silencioso de las siguientes páginas
            for (let i = 1; i <= HISTORY_PREFETCH; i++) {
                const nextPage = page + i;
                const totalPages = Math.max(1, Math.ceil(historyTotal / HISTORY_PAGE_SIZE));
                if (nextPage > totalPages) break;
                if (!historyCache.has(cacheKey(historyQuery, nextPage))) {
                    fetchHistoryPage(nextPage).catch(() => {});
                }
            }
        } catch (e) {
            console.error('loadHistoryPage error', e);
            if (historyTableBody) {
                historyTableBody.innerHTML =
                    '<tr><td colspan="6" class="bk-empty">Error al cargar el historial.</td></tr>';
            }
        }
    }

    function renderEmpty() {
        if (jobsList)         jobsList.innerHTML = '<div class="bk-empty">Sin datos</div>';
        if (destinationsList) destinationsList.innerHTML = '<div class="bk-empty">Sin datos</div>';
        if (historyTableBody) historyTableBody.innerHTML = '<tr><td colspan="6" class="bk-empty">Sin datos</td></tr>';
    }

    // ── Render ───────────────────────────────────────────────────────
    function fmtRelative(isoStr) {
        if (!isoStr) return '—';
        const diff = Date.now() - new Date(isoStr).getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 1)  return 'Hace menos de 1 min';
        if (mins < 60) return `Hace ${mins} min`;
        const hrs = Math.floor(mins / 60);
        if (hrs < 24)  return `Hace ${hrs} h`;
        const days = Math.floor(hrs / 24);
        return `Hace ${days} días`;
    }

    function renderSummary(s) {
        const total  = document.getElementById('totalBackups');
        const last   = document.getElementById('lastBackupDate');
        const age    = document.getElementById('lastBackupAge');
        const dot    = document.getElementById('lastBackupStatusDot');
        if (total) total.textContent = s.total_jobs ?? 0;
        if (last)  last.textContent  = s.last_backup ? fmtDate(s.last_backup) : '—';
        if (age)   age.textContent   = s.last_backup ? fmtRelative(s.last_backup) : '—';
        if (dot) {
            if (s.last_backup_status === 'completed') {
                dot.style.display = 'inline-block';
                dot.style.background = '#38B000';
                dot.title = 'Última copia completada';
            } else if (s.last_backup_status === 'error') {
                dot.style.display = 'inline-block';
                dot.style.background = '#dc2626';
                dot.title = 'Última copia fallida';
            } else if (s.last_backup_status === 'running') {
                dot.style.display = 'inline-block';
                dot.style.background = '#f59e0b';
                dot.title = 'Copia en curso';
            } else {
                dot.style.display = 'none';
            }
        }
    }

    async function refreshSummary() {
        try {
            const s = await api('GET', '/api/backup/summary');
            renderSummary(s);
        } catch (e) {
            console.warn('refreshSummary error', e);
        }
    }

    function renderDestinations() {
        if (!destinationsList) return;
        if (destinations.length === 0) {
            destinationsList.innerHTML = '<div class="bk-empty">No hay destinos configurados</div>';
        } else {
            destinationsList.innerHTML = destinations.map(d => {
                const dot = d.status === 'online' ? '' : (d.status === 'offline' ? 'offline' : 'unknown');
                const unsupp = d.supported ? '' : ' <span class="bk-tag-warn">no soportado</span>';
                return `
                    <div class="destination-item" data-id="${d.id}">
                        <div class="destination-info">
                            <div class="destination-name">${escapeHtml(d.name)}${unsupp}</div>
                            <div class="destination-path">${escapeHtml(d.path)}</div>
                            <div class="destination-type">${destTypeLabel(d.type)}</div>
                        </div>
                        <div class="destination-status">
                            <div class="connection-indicator ${dot}"></div>
                            <button class="job-action-btn" data-action="test-dest" data-id="${d.id}">Probar</button>
                            ${canWrite ? `<button class="job-action-btn" data-action="edit-dest" data-id="${d.id}">Editar</button>` : ''}
                            ${canWrite ? `<button class="job-action-btn danger" data-action="del-dest" data-id="${d.id}">Eliminar</button>` : ''}
                        </div>
                    </div>`;
            }).join('');
        }
        // Actualizar dropdowns
        const hint = document.getElementById('jobDestHint');
        document.querySelectorAll('#jobDestination').forEach(sel => {
            if (destinations.length === 0) {
                sel.innerHTML = '<option value="" disabled selected>— Crea un destino primero —</option>';
            } else {
                sel.innerHTML = destinations
                    .map(d => `<option value="${d.id}" ${d.supported ? '' : 'disabled'}>${escapeHtml(d.name)} (${escapeHtml(d.path)})${d.supported ? '' : ' — no soportado'}</option>`)
                    .join('');
            }
        });
        if (hint) hint.style.display = destinations.length === 0 ? 'block' : 'none';
    }

    function renderJobs() {
        if (!jobsList) return;
        if (jobs.length === 0) {
            jobsList.innerHTML = '<div class="bk-empty">No hay trabajos configurados</div>';
            return;
        }
        jobsList.innerHTML = jobs.map(job => {
            const dest = destinations.find(d => d.id === job.destination_id);
            const destName = dest ? dest.name : '—';
            const stClass = !job.enabled ? 'disabled'
                : (job.last_run && job.last_run.status === 'error') ? 'error'
                : job.schedule === 'manual' ? 'active' : 'scheduled';
            const stText = !job.enabled ? 'Desactivado'
                : (job.last_run && job.last_run.status === 'error') ? 'Error'
                : job.schedule === 'manual' ? 'Manual' : 'Programado';
            return `
                <div class="job-item" data-id="${job.id}">
                    <div class="job-info">
                        <div class="job-name">${escapeHtml(job.name)}</div>
                        <div class="job-details">
                            Tipo: ${backupTypeLabel(job.backup_type)} |
                            Destino: ${escapeHtml(destName)} |
                            ${scheduleLabel(job.schedule, job.schedule_time)}
                            ${job.next_run_at ? ' | Próx.: ' + fmtDate(job.next_run_at) : ''}
                        </div>
                    </div>
                    <div class="job-status">
                        <span class="status-badge ${stClass}">${stText}</span>
                        <div class="job-actions">
                            ${canWrite ? `<button class="job-action-btn" data-action="run" data-id="${job.id}" ${job.enabled ? '' : 'disabled'}>Ejecutar</button>` : ''}
                            ${canWrite && job.scheduled_task_name ? `<button class="job-action-btn" data-action="run-sched" data-id="${job.id}" title="Forzar la ejecución de la tarea programada de Windows">Probar tarea</button>` : ''}
                            ${job.scheduled_task_name ? `<button class="job-action-btn" data-action="sched-log" data-id="${job.id}" title="Ver log de ejecuciones de la tarea programada">Ver log</button>` : ''}
                            ${canWrite ? `<button class="job-action-btn" data-action="edit" data-id="${job.id}">Editar</button>` : ''}
                            ${canWrite ? `<button class="job-action-btn" data-action="toggle" data-id="${job.id}">${job.enabled ? 'Desactivar' : 'Activar'}</button>` : ''}
                            ${canWrite ? `<button class="job-action-btn danger" data-action="del" data-id="${job.id}">Eliminar</button>` : ''}
                        </div>
                    </div>
                </div>`;
        }).join('');
    }

    function renderHistoryPage(rows) {
        if (!historyTableBody) return;
        const meta = document.getElementById('historyMeta');
        if (meta) {
            if (historyTotal === 0) {
                meta.textContent = historyQuery
                    ? `Sin resultados para "${historyQuery}"`
                    : 'Sin entradas';
            } else {
                const from = (historyPage - 1) * HISTORY_PAGE_SIZE + 1;
                const to   = Math.min(historyPage * HISTORY_PAGE_SIZE, historyTotal);
                meta.textContent = `Mostrando ${from}–${to} de ${historyTotal}`;
            }
        }
        if (!rows || rows.length === 0) {
            historyTableBody.innerHTML =
                '<tr><td colspan="6" class="bk-empty">Sin historial en esta página.</td></tr>';
            return;
        }
        const STATUS_LABEL = {
            completed: 'Completado',
            error:     'Fallido',
            running:   'Ejecutando',
            cancelled: 'Cancelado',
        };
        historyTableBody.innerHTML = rows.map(h => {
            const cls = h.status === 'completed' ? 'completed'
                      : h.status === 'error'     ? 'error'
                      : h.status === 'running'   ? 'running'
                      : h.status === 'cancelled' ? 'cancelled' : '';
            const restoreBtn = (canWrite && h.status === 'completed')
                ? `<button class="job-action-btn" data-action="restore-h" data-id="${h.id}">Restaurar</button>` : '';
            const delBtn = canWrite
                ? `<button class="job-action-btn danger" data-action="del-h" data-id="${h.id}">Eliminar</button>` : '';
            const rowClass = h.status === 'error' ? ' class="history-row-error"' : '';
            const orphanTag = h.job_deleted
                ? ' <span class="bk-tag-warn" title="El trabajo origen fue eliminado">huérfano</span>'
                : '';
            const label = STATUS_LABEL[h.status] || h.status;
            return `
                <tr data-id="${h.id}"${rowClass}>
                    <td>${fmtDate(h.started_at)}</td>
                    <td>${escapeHtml(h.job_name)}${orphanTag}</td>
                    <td>${backupTypeLabel(h.backup_type)}</td>
                    <td>${fmtBytes(h.bytes_done)}</td>
                    <td><span class="status-badge ${cls}">${label}</span></td>
                    <td>
                        <button class="job-action-btn" data-action="view-h" data-id="${h.id}">Ver</button>
                        ${restoreBtn}
                        ${delBtn}
                    </td>
                </tr>`;
        }).join('');
    }

    function renderHistoryPagination() {
        const cont = document.getElementById('historyPagination');
        if (!cont) return;
        const totalPages = Math.max(1, Math.ceil(historyTotal / HISTORY_PAGE_SIZE));
        if (historyTotal <= HISTORY_PAGE_SIZE) {
            cont.innerHTML = '';
            return;
        }
        // Construir conjunto de páginas visibles: 1, ..., page-1, page, page+1, ..., last
        const pages = new Set([1, totalPages, historyPage - 1, historyPage, historyPage + 1]);
        const visible = Array.from(pages).filter(p => p >= 1 && p <= totalPages).sort((a, b) => a - b);
        let html = '';
        html += `<button class="bk-page-btn" data-page="${historyPage - 1}" ${historyPage <= 1 ? 'disabled' : ''}>« Anterior</button>`;
        let last = 0;
        for (const p of visible) {
            if (last && p - last > 1) html += `<span class="bk-page-gap">…</span>`;
            const cls = (p === historyPage) ? ' active' : '';
            html += `<button class="bk-page-btn${cls}" data-page="${p}">${p}</button>`;
            last = p;
        }
        html += `<button class="bk-page-btn" data-page="${historyPage + 1}" ${historyPage >= totalPages ? 'disabled' : ''}>Siguiente »</button>`;
        cont.innerHTML = html;
    }

    // ── Modales: helpers ─────────────────────────────────────────────
    function closeModal(modal) { if (modal) modal.style.display = 'none'; }

    // ── Modal trabajo ────────────────────────────────────────────────
    function openJobModal(job) {
        editingJobId = job ? job.id : null;
        document.getElementById('jobModalTitle').textContent =
            job ? 'Editar Trabajo de Copia de Seguridad' : 'Nuevo Trabajo de Copia de Seguridad';
        document.getElementById('jobName').value = job ? job.name : '';
        document.getElementById('jobType').value = job ? job.backup_type : 'full';
        document.getElementById('jobSource').value = job ? job.source_path : '';
        document.getElementById('jobSchedule').value = job ? job.schedule : 'manual';
        document.getElementById('jobTime').value = job ? job.schedule_time : '02:00';
        document.getElementById('jobCompress').checked = job ? job.compress : true;
        document.getElementById('jobVerify').checked   = job ? job.verify_after : true;
        document.getElementById('jobNotify').checked   = job ? job.notify : false;
        // destino
        renderDestinations();
        const sel = document.getElementById('jobDestination');
        if (sel && job) sel.value = job.destination_id;
        // Mostrar/ocultar hora
        const stg = document.getElementById('scheduleTimeGroup');
        if (stg) stg.style.display = (document.getElementById('jobSchedule').value === 'manual') ? 'none' : 'block';
        // limpiar checkboxes predefinidos
        document.querySelectorAll('.predefined-sources input[type="checkbox"]').forEach(cb => cb.checked = false);
        backupJobModal.style.display = 'block';
    }

    async function saveJob() {
        const payload = {
            name:           (document.getElementById('jobName').value || '').trim(),
            backup_type:    document.getElementById('jobType').value,
            source_path:    (document.getElementById('jobSource').value || '').trim(),
            destination_id: parseInt(document.getElementById('jobDestination').value, 10),
            schedule:       document.getElementById('jobSchedule').value,
            schedule_time:  document.getElementById('jobTime').value,
            compress:       document.getElementById('jobCompress').checked,
            verify_after:   document.getElementById('jobVerify').checked,
            notify:         document.getElementById('jobNotify').checked,
        };
        if (!payload.name || !payload.source_path || !payload.destination_id) {
            toast('Completa nombre, origen y destino.', true);
            return;
        }
        try {
            const resp = editingJobId
                ? await api('PUT',  '/api/backup/jobs/' + editingJobId, payload)
                : await api('POST', '/api/backup/jobs', payload);
            closeModal(backupJobModal);
            await loadAll();
            if (resp && resp.warning) {
                toast(resp.warning, true);
            }
        } catch (e) {
            toast('Error al guardar: ' + e.message, true);
        }
    }

    async function deleteJob(id) {
        if (!confirm('¿Eliminar este trabajo de backup?')) return;
        try {
            await api('DELETE', '/api/backup/jobs/' + id);
            await loadAll();
        } catch (e) {
            toast('Error al eliminar: ' + e.message, true);
        }
    }

    async function toggleJob(id) {
        try {
            await api('POST', '/api/backup/jobs/' + id + '/toggle');
            await loadAll();
        } catch (e) {
            toast('Error al cambiar estado: ' + e.message, true);
        }
    }

    async function runJob(id) {
        try {
            const resp = await api('POST', '/api/backup/jobs/' + id + '/run');
            const run  = resp.run;
            const job  = jobs.find(j => j.id === id);
            startProgress(run, job ? job.name : 'Backup');
            // Muestra la entrada "Ejecutando" en el historial sin esperar a que termine
            reloadHistory();
        } catch (e) {
            toast('Error al lanzar el backup: ' + e.message, true);
        }
    }

    async function runScheduledTask(id) {
        if (!confirm('Esto forzará la ejecución de la tarea programada de Windows ahora mismo (como SYSTEM). ¿Continuar?')) return;
        try {
            const resp = await api('POST', '/api/backup/jobs/' + id + '/run_scheduled');
            toast(resp.success
                ? 'Tarea iniciada. Espera unos segundos y pulsa "Ver log" para confirmar que ejecutó.'
                : ('Salida:\n\n' + (resp.output || '')),
                !resp.success);
        } catch (e) {
            toast('Error al iniciar la tarea: ' + e.message, true);
        }
    }

    async function showScheduledLog(id) {
        try {
            const resp = await api('GET', '/api/backup/jobs/' + id + '/scheduled_log');
            toast(resp.output || 'Sin entradas en el log todavía.', false);
        } catch (e) {
            toast('Error al leer el log: ' + e.message, true);
        }
    }

    // ── Modal destino ────────────────────────────────────────────────
    function openDestModal(dest) {
        editingDestId = dest ? dest.id : null;
        document.getElementById('destinationName').value = dest ? dest.name : '';
        document.getElementById('destinationType').value = dest ? dest.type : 'local';
        document.getElementById('destinationPath').value = dest ? dest.path : '';
        document.getElementById('destinationUser').value = '';
        document.getElementById('destinationPassword').value = '';
        document.getElementById('credentialsGroup').style.display =
            (dest && ['network', 'cloud', 'ftp'].includes(dest.type)) ? 'block' : 'none';
        // Solo 'local' está implementado; los demás tipos están deshabilitados
        Array.from(document.getElementById('destinationType').options).forEach(opt => {
            opt.disabled = opt.value !== 'local';
        });
        destinationModal.style.display = 'block';
    }

    async function saveDest() {
        const payload = {
            name: (document.getElementById('destinationName').value || '').trim(),
            type: document.getElementById('destinationType').value,
            path: (document.getElementById('destinationPath').value || '').trim(),
        };
        if (!payload.name || !payload.path) {
            toast('Completa nombre y ruta.', true);
            return;
        }
        try {
            if (editingDestId) {
                await api('PUT', '/api/backup/destinations/' + editingDestId, payload);
            } else {
                await api('POST', '/api/backup/destinations', payload);
            }
            closeModal(destinationModal);
            await loadAll();
        } catch (e) {
            toast('Error al guardar destino: ' + e.message, true);
        }
    }

    async function deleteDest(id) {
        if (!confirm('¿Eliminar este destino?')) return;
        try {
            await api('DELETE', '/api/backup/destinations/' + id);
            await loadAll();
        } catch (e) {
            toast('Error al eliminar: ' + e.message, true);
        }
    }

    async function testDest(id) {
        try {
            const resp = await api('POST', '/api/backup/destinations/' + id + '/test');
            const ok = resp.destination && resp.destination.status === 'online';
            toast(ok ? 'Destino accesible.' : (resp.message || 'Destino no accesible.'), !ok);
            await loadAll();
        } catch (e) {
            toast('Error al probar destino: ' + e.message, true);
        }
    }

    // ── Historial ────────────────────────────────────────────────────
    function findHistoryRow(id) {
        for (const rows of historyCache.values()) {
            const row = rows.find(h => h.id === id);
            if (row) return row;
        }
        return null;
    }

    async function fetchHistoryRow(id) {
        try {
            const r = await api('GET', '/api/backup/history/' + id);
            return r.run || null;
        } catch (_) {
            return null;
        }
    }

    async function viewHistory(id) {
        let item = findHistoryRow(id) || await fetchHistoryRow(id);
        if (!item) return;
        const title = document.getElementById('detailsModalTitle');
        const cont  = document.getElementById('backupDetailsContent');
        if (title) title.textContent = 'Detalles: ' + item.job_name;
        if (cont) {
            cont.innerHTML = `
                <div class="detail-section">
                    <h4>Información General</h4>
                    <div class="detail-item"><strong>Trabajo:</strong><span>${escapeHtml(item.job_name)}</span></div>
                    <div class="detail-item"><strong>Tipo:</strong><span>${backupTypeLabel(item.backup_type)}</span></div>
                    <div class="detail-item"><strong>Inicio:</strong><span>${fmtDate(item.started_at)}</span></div>
                    <div class="detail-item"><strong>Fin:</strong><span>${item.finished_at ? fmtDate(item.finished_at) : '—'}</span></div>
                    <div class="detail-item"><strong>Duración:</strong><span>${item.duration_sec != null ? fmtDuration(item.duration_sec) : '—'}</span></div>
                    <div class="detail-item"><strong>Estado:</strong><span class="status-badge ${item.status}">${item.status}</span></div>
                </div>
                <div class="detail-section">
                    <h4>Estadísticas</h4>
                    <div class="detail-item"><strong>Tamaño:</strong><span>${fmtBytes(item.bytes_done)}</span></div>
                    <div class="detail-item"><strong>Archivos:</strong><span>${item.files_done || 0}</span></div>
                    <div class="detail-item"><strong>Ruta:</strong><span style="word-break:break-all">${escapeHtml(item.backup_path || '—')}</span></div>
                </div>
                ${item.error ? `<div class="detail-section"><h4>Error</h4><div class="detail-item"><span style="color:#d9534f">${escapeHtml(item.error)}</span></div></div>` : ''}
                ${item.output ? `<div class="detail-section"><h4>Salida</h4><pre class="command-output" style="white-space:pre-wrap;max-height:200px;overflow:auto">${escapeHtml(item.output)}</pre></div>` : ''}
            `;
        }
        backupDetailsModal.dataset.runId = id;
        backupDetailsModal.style.display = 'block';
    }

    async function restoreHistory(id) {
        const item = findHistoryRow(id) || await fetchHistoryRow(id);
        if (!item) return;
        const restorePath = prompt(
            `Restaurar "${item.job_name}" del ${fmtDate(item.started_at)}\n\n` +
            `Ruta de destino para la restauración:`,
            'C:\\Restore'
        );
        if (!restorePath) return;
        const overwrite = confirm('¿Sobrescribir archivos existentes en el destino?');
        try {
            const resp = await api('POST', '/api/backup/history/' + id + '/restore',
                                   { restore_path: restorePath, overwrite });
            toast(resp.success ? 'Restauración completada.' : ('Restauración con incidencias:\n\n' + (resp.output || '')), !resp.success);
        } catch (e) {
            toast('Error al restaurar: ' + e.message, true);
        }
    }

    async function deleteHistoryEntry(id) {
        if (!confirm('¿Eliminar este registro del historial?\n\nSi confirmas con OK, también se preguntará si quieres eliminar el archivo del disco.')) return;
        const onDisk = confirm('¿Eliminar también el archivo de copia del disco?');
        try {
            await api('DELETE', '/api/backup/history/' + id + (onDisk ? '?delete_disk=true' : ''));
            closeModal(backupDetailsModal);
            await loadAll();
        } catch (e) {
            toast('Error al eliminar: ' + e.message, true);
        }
    }

    // ── Progreso (polling) ───────────────────────────────────────────
    function startProgress(run, label) {
        currentRunId = run.id;
        progressPanel.style.display = 'block';
        document.getElementById('progressTitle').textContent = 'Ejecutando: ' + label;
        progressFill.style.width = '0%';
        progressText.textContent = '0%';
        progressDetails.textContent = 'Iniciando…';
        progressFiles.textContent = '0 archivos';
        progressSize.textContent  = '0 B';
        progressTime.textContent  = '00:00';
        if (pollTimer) clearInterval(pollTimer);
        const startedAt = new Date(run.started_at).getTime();
        pollTimer = setInterval(async () => {
            try {
                const resp = await api('GET', '/api/backup/runs/' + currentRunId);
                const r = resp.run;
                progressFill.style.width = (r.progress_pct || 0) + '%';
                progressText.textContent = Math.floor(r.progress_pct || 0) + '%';
                progressFiles.textContent = (r.files_done || 0) + ' archivos';
                progressSize.textContent  = fmtBytes(r.bytes_done);
                const elapsed = Math.floor((Date.now() - startedAt) / 1000);
                progressTime.textContent  = fmtDuration(elapsed);
                progressDetails.textContent =
                    r.status === 'running'   ? 'Copiando…' :
                    r.status === 'completed' ? 'Backup completado.' :
                    r.status === 'error'     ? ('Error: ' + (r.error || 'desconocido')) : r.status;
                if (r.status !== 'running') {
                    clearInterval(pollTimer);
                    pollTimer = null;
                    await loadAll();
                    progressPanel.style.display = 'none';
                }
            } catch (e) {
                console.warn('poll error', e);
                if (e.status === 404) {
                    clearInterval(pollTimer);
                    pollTimer = null;
                    progressPanel.style.display = 'none';
                }
            }
        }, 1500);
    }

    // ── Listeners ────────────────────────────────────────────────────
    function setupEventListeners() {
        if (createBackupJobBtn) createBackupJobBtn.addEventListener('click', () => openJobModal(null));
        if (addDestinationBtn)  addDestinationBtn.addEventListener('click', () => openDestModal(null));
        if (refreshHistoryBtn)  refreshHistoryBtn.addEventListener('click', () => reloadHistory());
        const refreshSummaryBtn = document.getElementById('refreshSummaryBtn');
        if (refreshSummaryBtn)  refreshSummaryBtn.addEventListener('click', refreshSummary);

        // Buscador del historial (debounced)
        const searchInput = document.getElementById('historySearch');
        if (searchInput) {
            searchInput.addEventListener('input', function () {
                clearTimeout(historySearchTimer);
                const q = this.value.trim();
                historySearchTimer = setTimeout(() => {
                    if (q === historyQuery) return;
                    historyQuery = q;
                    invalidateHistoryCache();
                    historyPage = 1;
                    loadHistoryPage(1);
                }, 300);
            });
        }
        // Paginación: clicks delegados
        const pagination = document.getElementById('historyPagination');
        if (pagination) {
            pagination.addEventListener('click', function (ev) {
                const btn = ev.target.closest('button[data-page]');
                if (!btn || btn.disabled) return;
                const page = parseInt(btn.dataset.page, 10);
                if (page && page !== historyPage) loadHistoryPage(page);
            });
        }

        document.querySelectorAll('.option-btn, [data-backup-type]').forEach(btn => {
            btn.addEventListener('click', function () {
                const type = this.getAttribute('data-backup-type');
                openJobModal(null);
                applyPreset(type);
            });
        });

        document.querySelectorAll('.close-button').forEach(btn => {
            btn.addEventListener('click', function () {
                closeModal(this.closest('.modal, .bk-modal'));
            });
        });
        window.addEventListener('click', (ev) => {
            if (ev.target.classList.contains('modal') || ev.target.classList.contains('bk-modal')) {
                closeModal(ev.target);
            }
        });

        if (closeProgressBtn) closeProgressBtn.addEventListener('click', () => {
            progressPanel.style.display = 'none';
            // No se cancela el poll: el backup sigue corriendo en background y
            // al terminar (éxito o error) actualiza el summary y el historial.
        });

        // Modal trabajo
        const saveJobBtn   = document.getElementById('saveJobBtn');
        const cancelJobBtn = document.getElementById('cancelJobBtn');
        if (saveJobBtn)   saveJobBtn.addEventListener('click', saveJob);
        if (cancelJobBtn) cancelJobBtn.addEventListener('click', () => closeModal(backupJobModal));
        const jobSchedule = document.getElementById('jobSchedule');
        if (jobSchedule) jobSchedule.addEventListener('change', function () {
            const stg = document.getElementById('scheduleTimeGroup');
            if (stg) stg.style.display = this.value === 'manual' ? 'none' : 'block';
        });
        const quickDestBtn = document.getElementById('quickCreateDestBtn');
        if (quickDestBtn) quickDestBtn.addEventListener('click', () => openDestModal(null));

        const browseBtn = document.getElementById('browseSourceBtn');
        if (browseBtn) browseBtn.addEventListener('click', function () {
            const choices = [
                'C:\\Users\\Public\\Documents',
                'C:\\Program Files',
                'D:\\Datos',
            ];
            const cur = document.getElementById('jobSource').value;
            const picked = prompt(
                'Introduce la ruta a respaldar (Windows absoluto):\n\nSugerencias:\n  ' + choices.join('\n  '),
                cur || choices[0]
            );
            if (picked) document.getElementById('jobSource').value = picked.trim();
        });
        document.querySelectorAll('.predefined-sources input[type="checkbox"]').forEach(cb => {
            cb.addEventListener('change', function () {
                const src = document.getElementById('jobSource');
                const sources = Array.from(document.querySelectorAll('.predefined-sources input[type="checkbox"]:checked'))
                    .map(c => c.value);
                if (sources.length === 1) src.value = sources[0];
            });
        });

        // Modal destino
        const saveDestBtn = document.getElementById('saveDestinationBtn');
        const testDestBtn = document.getElementById('testDestinationBtn');
        const cancelDestBtn = document.getElementById('cancelDestinationBtn');
        if (saveDestBtn) saveDestBtn.addEventListener('click', saveDest);
        if (cancelDestBtn) cancelDestBtn.addEventListener('click', () => closeModal(destinationModal));
        if (testDestBtn) testDestBtn.addEventListener('click', async function () {
            // Si estamos editando, prueba el ID; si es nuevo, primero exige guardar.
            if (editingDestId) {
                await testDest(editingDestId);
            } else {
                toast('Guarda el destino antes de probarlo.', false);
            }
        });
        const destType = document.getElementById('destinationType');
        if (destType) destType.addEventListener('change', function () {
            const cred = document.getElementById('credentialsGroup');
            cred.style.display = ['network', 'cloud', 'ftp'].includes(this.value) ? 'block' : 'none';
        });

        // Modal detalles
        const restoreBtn = document.getElementById('restoreBackupBtn');
        const deleteBtn  = document.getElementById('deleteBackupBtn');
        const closeDet   = document.getElementById('closeDetailsBtn');
        if (restoreBtn) restoreBtn.addEventListener('click', () => {
            const id = parseInt(backupDetailsModal.dataset.runId, 10);
            if (id) restoreHistory(id);
        });
        if (deleteBtn) deleteBtn.addEventListener('click', () => {
            const id = parseInt(backupDetailsModal.dataset.runId, 10);
            if (id) deleteHistoryEntry(id);
        });
        if (closeDet) closeDet.addEventListener('click', () => closeModal(backupDetailsModal));

        // Listeners delegados
        if (jobsList) jobsList.addEventListener('click', function (ev) {
            const btn = ev.target.closest('button[data-action]');
            if (!btn) return;
            const id = parseInt(btn.dataset.id, 10);
            switch (btn.dataset.action) {
                case 'run':       runJob(id); break;
                case 'run-sched': runScheduledTask(id); break;
                case 'sched-log': showScheduledLog(id); break;
                case 'edit':      openJobModal(jobs.find(j => j.id === id)); break;
                case 'toggle':    toggleJob(id); break;
                case 'del':       deleteJob(id); break;
            }
        });
        if (destinationsList) destinationsList.addEventListener('click', function (ev) {
            const btn = ev.target.closest('button[data-action]');
            if (!btn) return;
            const id = parseInt(btn.dataset.id, 10);
            switch (btn.dataset.action) {
                case 'edit-dest': openDestModal(destinations.find(d => d.id === id)); break;
                case 'del-dest':  deleteDest(id); break;
                case 'test-dest': testDest(id); break;
            }
        });
        if (historyTableBody) historyTableBody.addEventListener('click', function (ev) {
            const btn = ev.target.closest('button[data-action]');
            if (!btn) return;
            const id = parseInt(btn.dataset.id, 10);
            switch (btn.dataset.action) {
                case 'view-h':    viewHistory(id); break;
                case 'restore-h': restoreHistory(id); break;
                case 'del-h':     deleteHistoryEntry(id); break;
            }
        });

        // Cambio de máquina
        window.addEventListener('machineChanged', loadAll);
    }

    function applyPreset(type) {
        const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
        switch (type) {
            case 'system':
                set('jobName', 'Backup_Sistema');
                set('jobSource', 'C:\\');
                set('jobType', 'full');
                set('jobSchedule', 'weekly');
                break;
            case 'documents':
                set('jobName', 'Backup_Documentos');
                set('jobSource', 'C:\\Users\\Public\\Documents');
                set('jobType', 'incremental');
                set('jobSchedule', 'daily');
                break;
            case 'applications':
                set('jobName', 'Backup_Aplicaciones');
                set('jobSource', 'C:\\Program Files');
                set('jobType', 'differential');
                set('jobSchedule', 'weekly');
                break;
            case 'custom':
                set('jobName', 'Backup_Personalizado');
                set('jobType', 'incremental');
                set('jobSchedule', 'manual');
                break;
        }
        const stg = document.getElementById('scheduleTimeGroup');
        if (stg) stg.style.display = (document.getElementById('jobSchedule').value === 'manual') ? 'none' : 'block';
    }

    // ── Salud del servidor ───────────────────────────────────────────
    async function checkServerConnection() {
        try {
            const r = await fetch('/health');
            const d = await r.json();
            updateStatus(d.status === 'ok' ? 'connected' : 'error');
        } catch (_) {
            updateStatus('error');
        }
    }

    // ── Init ─────────────────────────────────────────────────────────
    setupEventListeners();
    checkServerConnection();
    loadAll();
    setInterval(() => {
        if (document.visibilityState === 'visible') checkServerConnection();
    }, 30000);
});
