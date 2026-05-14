// static/js/disk_partition.js
// Gestión de particiones de disco. Sin panel de herramientas.

document.addEventListener('DOMContentLoaded', function () {
    // ── DOM refs ─────────────────────────────────────────────────────
    const statusIndicator   = document.getElementById('status-indicator');
    const disksList         = document.getElementById('disksList');
    const diskDetailTitle   = document.getElementById('diskDetailTitle');
    const diskProperties    = document.getElementById('diskProperties');
    const partitionsBody    = document.getElementById('partitionsBody');
    const partitionsVisual  = document.getElementById('partitionsVisual');

    const refreshDisksBtn   = document.getElementById('refreshDisks');
    const createPartBtn     = document.getElementById('createPartition');
    const formatPartBtn     = document.getElementById('formatPartition');
    const deletePartBtn     = document.getElementById('deletePartition');

    const diskModal         = document.getElementById('diskModal');
    const commandModal      = document.getElementById('commandModal');
    const modalTitle        = document.getElementById('modalTitle');
    const modalContent      = document.getElementById('modalContent');
    const cancelOpBtn       = document.getElementById('cancelOperation');
    const confirmOpBtn      = document.getElementById('confirmOperation');
    const closeDiskModalBtn = document.getElementById('closeDiskModal');
    const closeCmdModalBtn  = document.getElementById('closeCommandModal');
    const cmdTitle          = document.getElementById('commandModalTitle');
    const cmdOutput         = document.getElementById('commandOutput');

    // ── Estado ───────────────────────────────────────────────────────
    let disksData       = [];
    let partitionsData  = [];
    let currentDiskId   = null;
    let currentPartId   = null;

    // ── Helpers ──────────────────────────────────────────────────────
    function mid() {
        return (window.MS && window.MS.getMachineId && window.MS.getMachineId()) || null;
    }
    function machineQ(sep) {
        const m = mid();
        return m ? sep + 'machine_id=' + encodeURIComponent(m) : '';
    }

    async function api(method, path, body) {
        const opts = { method, headers: { 'Accept': 'application/json' } };
        if (body !== undefined && method !== 'GET') {
            opts.headers['Content-Type'] = 'application/json';
            opts.body = JSON.stringify(Object.assign({}, body, mid() ? { machine_id: mid() } : {}));
        }
        const url = path + (path.includes('?') ? machineQ('&') : machineQ('?'));
        const res = await fetch(url, opts);
        let data = null;
        try { data = await res.json(); } catch (_) {}
        if (!res.ok) {
            const msg = (data && data.error) || `HTTP ${res.status}`;
            const err = new Error(msg);
            err.status = res.status;
            err.data = data;
            throw err;
        }
        return data;
    }

    function escapeHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function fmtGb(n) {
        n = parseFloat(n) || 0;
        return n >= 1024 ? (n / 1024).toFixed(2) + ' TB' : n.toFixed(2) + ' GB';
    }

    function showResult(title, text, isError) {
        if (cmdTitle)  cmdTitle.textContent = title || 'Resultado';
        if (cmdOutput) {
            cmdOutput.textContent = text || '';
            cmdOutput.style.color = isError ? '#dc2626' : '';
        }
        if (commandModal) commandModal.style.display = 'flex';
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

    function setLastUpdate() {
        const el = document.getElementById('lastUpdate');
        if (!el) return;
        const d = new Date();
        el.textContent = d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }

    // ── Carga ────────────────────────────────────────────────────────
    async function loadDisks() {
        updateStatus('loading');
        try {
            disksData = await api('GET', '/api/particiones/disks') || [];
            renderDisks();
            updateSummary();
            updateStatus('connected');
            setLastUpdate();
            // Si el disco actual no existe, selecciona el primero
            const stillExists = disksData.some(d => d.id === currentDiskId);
            if (!stillExists && disksData.length > 0) {
                selectDisk(disksData[0].id);
            } else if (currentDiskId) {
                selectDisk(currentDiskId, /*force*/true);
            }
        } catch (e) {
            console.error('loadDisks error', e);
            updateStatus('error');
            disksData = [];
            renderDisks();
        }
    }

    async function loadPartitions(diskId) {
        try {
            partitionsData = await api('GET', '/api/particiones/partitions?disk_id=' + encodeURIComponent(diskId)) || [];
            renderPartitions();
            updateSummary();
        } catch (e) {
            console.error('loadPartitions error', e);
            partitionsData = [];
            renderPartitions();
        }
    }

    async function loadDiskDetail(diskId) {
        try {
            const d = await api('GET', '/api/particiones/disk_detail?disk_id=' + encodeURIComponent(diskId));
            renderDiskDetail(d);
        } catch (e) {
            console.error('loadDiskDetail error', e);
            if (diskDetailTitle) diskDetailTitle.textContent = 'Detalles del Disco';
            if (diskProperties)  diskProperties.innerHTML  = '<div class="text-muted">No se pudieron cargar los detalles.</div>';
        }
    }

    // ── Render ───────────────────────────────────────────────────────
    function renderDisks() {
        if (!disksList) return;
        if (disksData.length === 0) {
            disksList.innerHTML = '<div class="text-muted">No se encontraron discos físicos</div>';
            return;
        }
        disksList.innerHTML = disksData.map(d => {
            const sel = d.id === currentDiskId ? ' selected' : '';
            const usage = parseFloat(d.usage_percent) || 0;
            return `
                <div class="disk-item${sel}" data-disk-id="${escapeHtml(d.id)}">
                    <div class="disk-name">${escapeHtml(d.name || ('Disco ' + d.number))}</div>
                    <div class="disk-health health-${escapeHtml(d.health || 'unknown')}">Estado: ${escapeHtml(d.status || '—')}</div>
                    <div class="disk-info">
                        <div class="disk-chart-mini"><canvas id="diskChart_${escapeHtml(d.id)}"></canvas></div>
                        <div class="disk-usage">${usage.toFixed(1)}% Usado</div>
                    </div>
                </div>`;
        }).join('');
        // Crear los charts después
        disksData.forEach(d => {
            const el = document.getElementById('diskChart_' + d.id);
            if (el) drawDoughnut(el.getContext('2d'), parseFloat(d.usage_percent) || 0);
        });
    }

    function renderDiskDetail(d) {
        if (!d) return;
        if (diskDetailTitle) {
            diskDetailTitle.textContent = 'Detalles: ' + (d.name || ('Disco ' + d.id));
        }
        if (!diskProperties) return;
        const props = [
            ['Modelo',                 d.model || 'Desconocido'],
            ['Número de Serie',        d.serial || 'N/A'],
            ['Interfaz',               d.interface || 'N/A'],
            ['Tamaño',                 d.size || 'N/A'],
            ['Particiones',            d.partitions != null ? d.partitions : 'N/A'],
            ['Estado',                 d.status || 'Desconocido'],
            ['SMART',                  d.smart_status || 'N/A'],
            ['Temperatura',            d.temperature || 'N/A'],
            ['Horas de funcionamiento', d.hours || 'N/A'],
        ];
        const healthCls = d.health ? 'health-' + d.health : '';
        diskProperties.innerHTML = `
            <table class="properties-table">
                <tbody>
                    ${props.map(([k, v]) => {
                        const cls = (k === 'Estado' || k === 'SMART') ? healthCls : '';
                        return `<tr><th>${escapeHtml(k)}</th><td class="${cls}">${escapeHtml(v)}</td></tr>`;
                    }).join('')}
                </tbody>
            </table>`;
    }

    // Paleta para colores rotativos en orden estable (alineado con el CSS)
    const COLOR_PALETTE = [
        '#0A67DC', '#7C3AED', '#2EA043', '#F59E0B', '#EC4899',
        '#06B6D4', '#DC2626', '#84CC16', '#F97316', '#6366F1',
    ];

    // Devuelve [colorIdx 0..9, hexColor] para una partición. Las particiones especiales
    // (free/reserved/system/recovery) usan su propio color y no consumen ranura.
    function partitionColor(p, idx) {
        const t = (p.type || '').toLowerCase();
        if (t === 'free')     return [-1, '#cfd3d9'];
        if (t === 'reserved') return [-1, '#94a3b8'];
        const ci = idx % COLOR_PALETTE.length;
        return [ci, COLOR_PALETTE[ci]];
    }

    function renderPartitions() {
        if (!partitionsBody || !partitionsVisual) return;
        if (partitionsData.length === 0) {
            partitionsBody.innerHTML  = '<tr><td colspan="8" class="text-muted">No se encontraron particiones para este disco.</td></tr>';
            partitionsVisual.innerHTML = '<div class="partition-block free" style="width:100%">Sin particiones</div>';
            return;
        }
        const totalSize = partitionsData.reduce((acc, p) => acc + (parseFloat(p.size_gb) || 0), 0) || 1;

        // Pre-calcular color por índice (excluye especiales para no romper la rotación)
        let normalIdx = 0;
        const colorByPart = partitionsData.map(p => {
            const t = (p.type || '').toLowerCase();
            if (t === 'free' || t === 'reserved') return partitionColor(p, 0);
            const c = partitionColor(p, normalIdx);
            normalIdx += 1;
            return c;
        });

        partitionsBody.innerHTML = partitionsData.map((p, i) => {
            const sel  = p.id === currentPartId ? ' class="selected"' : '';
            const used = parseFloat(p.used_percent) || 0;
            const [, hex] = colorByPart[i];
            const dot = `<span class="part-color-dot" style="background:${hex}"></span>`;
            return `
                <tr data-partition="${escapeHtml(p.id)}"${sel}>
                    <td>${dot}${escapeHtml(p.letter || '-')}</td>
                    <td>${escapeHtml(p.label || 'Sin etiqueta')}</td>
                    <td>${escapeHtml(p.filesystem || '-')}</td>
                    <td>${fmtGb(p.size_gb)}</td>
                    <td>${fmtGb(p.used_gb)}</td>
                    <td>${fmtGb(p.free_gb)}</td>
                    <td>
                        <div class="progress-bar"><div class="progress" style="width:${Math.min(100, used)}%"></div></div>
                        <span style="font-size:11px;margin-left:4px">${used.toFixed(0)}%</span>
                    </td>
                    <td><span class="status-badge ${escapeHtml(p.status || 'free')}">${escapeHtml((p.status || 'free').replace(/^./, c => c.toUpperCase()))}</span></td>
                </tr>`;
        }).join('');

        partitionsVisual.innerHTML = partitionsData.map((p, i) => {
            const w = ((parseFloat(p.size_gb) || 0) / totalSize) * 100;
            const [ci] = colorByPart[i];
            const cls = (p.type || '').toLowerCase();
            const colorAttr = ci >= 0 ? ` data-color="${ci}"` : '';
            const selAttr = p.id === currentPartId ? ' selected' : '';
            const txt = p.letter
                ? `${p.letter}: (${fmtGb(p.size_gb)})`
                : `${p.type || 'Sin asignar'} (${fmtGb(p.size_gb)})`;
            return `<div class="partition-block ${escapeHtml(cls || 'free')}${selAttr}"
                data-partition="${escapeHtml(p.id)}"${colorAttr}
                style="width:${Math.max(5, w)}%"
                title="${escapeHtml(p.label || 'Sin etiqueta')} — ${escapeHtml(p.filesystem || 'Sin FS')} — ${(parseFloat(p.used_percent) || 0).toFixed(1)}% usado">
                ${escapeHtml(txt)}
            </div>`;
        }).join('');
    }

    function updateSummary() {
        const elDisks   = document.getElementById('summaryDisks');
        const elDisksT  = document.getElementById('summaryDisksTotal');
        const elParts   = document.getElementById('summaryPartitions');
        const elPartsT  = document.getElementById('summaryPartitionsTotal');
        const elFree    = document.getElementById('summaryFree');
        const elFreeT   = document.getElementById('summaryFreeTotal');
        const elSmart   = document.getElementById('summarySmart');
        const elSmartS  = document.getElementById('summarySmartSub');

        if (elDisks)  elDisks.textContent  = disksData.length;

        // Sumar tamaños totales (de los discos enriquecidos)
        const totalDiskGb = disksData.reduce((acc, d) => acc + (parseFloat(d.size_total_gb) || 0), 0);
        if (elDisksT) elDisksT.textContent = totalDiskGb > 0 ? `Total: ${fmtGb(totalDiskGb)}` : '—';

        // Particiones del disco actual (la API por disco) — si quieres global, hay que pedirlo aparte.
        const totalParts = partitionsData.length;
        const sizeParts  = partitionsData.reduce((a, p) => a + (parseFloat(p.size_gb) || 0), 0);
        const freeParts  = partitionsData.reduce((a, p) => a + (parseFloat(p.free_gb) || 0), 0);
        if (elParts)  elParts.textContent  = totalParts;
        if (elPartsT) elPartsT.textContent = sizeParts > 0 ? `Tamaño total: ${fmtGb(sizeParts)}` : '—';

        if (elFree)   elFree.textContent   = fmtGb(freeParts);
        if (elFreeT) {
            const pct = sizeParts > 0 ? (freeParts / sizeParts) * 100 : 0;
            elFreeT.textContent = sizeParts > 0 ? `${pct.toFixed(1)}% libre` : '—';
        }

        // SMART = peor estado de los discos
        if (elSmart && elSmartS) {
            let worst = 'good';
            for (const d of disksData) {
                if (d.health === 'critical') { worst = 'critical'; break; }
                if (d.health === 'warning' && worst !== 'critical') worst = 'warning';
                if (d.health === 'unknown' && worst === 'good') worst = 'unknown';
            }
            const labels = {
                good:     ['BUENO',         'Sin errores detectados'],
                warning:  ['ADVERTENCIA',   'Algunos discos con avisos'],
                critical: ['CRÍTICO',       '¡Atención! Problemas detectados'],
                unknown:  ['—',             'Estado desconocido'],
            };
            const [val, sub] = labels[worst];
            elSmart.textContent  = val;
            elSmart.className    = 'dp-card-value health-' + worst;
            elSmartS.textContent = sub;
        }
    }

    // ── Selección ────────────────────────────────────────────────────
    function selectDisk(diskId, force) {
        if (!force && diskId === currentDiskId) return;
        currentDiskId = diskId;
        currentPartId = null;
        // Actualizar marcador visual
        document.querySelectorAll('.disk-item').forEach(el => {
            el.classList.toggle('selected', el.dataset.diskId === diskId);
        });
        loadDiskDetail(diskId);
        loadPartitions(diskId);
    }

    function selectPartition(pid) {
        currentPartId = pid;
        document.querySelectorAll('#partitionsBody tr').forEach(tr => {
            tr.classList.toggle('selected', tr.dataset.partition === pid);
        });
    }

    // ── Doughnut chart ───────────────────────────────────────────────
    function drawDoughnut(ctx, pct) {
        if (!ctx || typeof Chart === 'undefined') return;
        const existing = Chart.getChart(ctx.canvas);
        if (existing) existing.destroy();
        new Chart(ctx, {
            type: 'doughnut',
            data: { datasets: [{ data: [pct, 100 - pct], backgroundColor: ['#0078d7', '#e0e0e0'], borderWidth: 0 }] },
            options: { cutout: '70%', responsive: true, maintainAspectRatio: true,
                       plugins: { legend: { display: false }, tooltip: { enabled: false } } }
        });
    }

    // ── Modal de operaciones de partición ────────────────────────────
    function openPartitionModal(operation) {
        if (!diskModal) return;
        if (operation === 'create' && !currentDiskId) {
            showResult('Selección requerida', 'Selecciona un disco para crear una partición.', true);
            return;
        }
        if ((operation === 'format' || operation === 'delete') && !currentPartId) {
            showResult('Selección requerida', 'Selecciona una partición primero.', true);
            return;
        }

        const titles = { create: 'Crear Nueva Partición', format: 'Formatear Partición', delete: 'Eliminar Partición' };
        if (modalTitle) modalTitle.textContent = titles[operation] || 'Operación';

        if (operation === 'create') {
            const disk = disksData.find(d => d.id === currentDiskId);
            const diskTotalGb = parseFloat(disk?.size_total_gb) || 0;
            const usedGb = partitionsData.reduce((a, p) => a + (parseFloat(p.size_gb) || 0), 0);
            // Si no hay particiones aún (disco vacío/sin inicializar) usar el tamaño
            // del disco como espacio libre. Si no hay tamaño, parsearlo del string.
            let totalFromString = 0;
            if (disk && disk.size) {
                const m = String(disk.size).match(/(\d+(?:\.\d+)?)\s*(TB|GB)/i);
                if (m) totalFromString = parseFloat(m[1]) * (m[2].toUpperCase() === 'TB' ? 1024 : 1);
            }
            const baseTotal = Math.max(diskTotalGb, totalFromString);
            const freeGb = Math.max(0, baseTotal - usedGb);

            // Letras ocupadas en TODOS los discos (no solo el actual)
            const usedLetters = new Set();
            // De partitionsData del disco actual:
            partitionsData.forEach(p => { if (p.letter) usedLetters.add(String(p.letter).toUpperCase()); });
            // De cualquier partición visible en la app (best-effort):
            (window._allPartitions || []).forEach(p => { if (p.letter) usedLetters.add(String(p.letter).toUpperCase()); });
            const RESERVED = new Set(['A', 'B', 'C']);
            const letterOpts = ['<option value="">— sin asignar —</option>'];
            for (let c = 'D'.charCodeAt(0); c <= 'Z'.charCodeAt(0); c++) {
                const L = String.fromCharCode(c);
                const taken = usedLetters.has(L) || RESERVED.has(L);
                letterOpts.push(`<option value="${L}" ${taken ? 'disabled' : ''}>${L}:${taken ? ' (en uso)' : ''}</option>`);
            }

            modalContent.innerHTML = `
                <div class="form-group"><label>Tamaño (GB):</label>
                    <input type="number" id="partitionSize" min="0.1" max="${freeGb.toFixed(2)}"
                        value="${Math.min(freeGb, 50).toFixed(2)}" step="0.1">
                </div>
                <div class="form-group"><label>Sistema de archivos:</label>
                    <select id="fileSystem">
                        <option value="NTFS">NTFS</option><option value="FAT32">FAT32</option>
                        <option value="exFAT">exFAT</option><option value="ReFS">ReFS</option>
                    </select>
                </div>
                <div class="form-group"><label>Letra de unidad (opcional):</label>
                    <select id="partitionLetter">${letterOpts.join('')}</select>
                </div>
                <div class="form-group"><label>Etiqueta (opcional):</label>
                    <input type="text" id="partitionLabel" placeholder="Nueva" maxlength="32">
                </div>
                <div class="form-group"><p>Espacio disponible estimado: ${freeGb.toFixed(2)} GB</p></div>`;
        } else if (operation === 'format') {
            const p = partitionsData.find(x => x.id === currentPartId);
            modalContent.innerHTML = `
                <div class="form-group"><label>Sistema de archivos:</label>
                    <select id="formatFileSystem">
                        <option value="NTFS">NTFS</option><option value="FAT32">FAT32</option>
                        <option value="exFAT">exFAT</option><option value="ReFS">ReFS</option>
                    </select>
                </div>
                <div class="form-group"><label>Etiqueta (opcional):</label>
                    <input type="text" id="formatLabel" placeholder="${escapeHtml(p?.label || '')}" maxlength="32">
                </div>
                <div class="form-group"><p class="warning">ADVERTENCIA: el formateo elimina todos los datos de la partición.</p></div>`;
        } else if (operation === 'delete') {
            const p = partitionsData.find(x => x.id === currentPartId);
            if (!p) {
                showResult('Error', 'No se pudo encontrar la partición seleccionada.', true);
                return;
            }
            modalContent.innerHTML = `
                <div class="form-group">
                    <p>Vas a eliminar:</p>
                    <p><strong>${escapeHtml(p.letter || 'Sin letra')} — ${escapeHtml(p.label || 'Sin etiqueta')} (${fmtGb(p.size_gb)})</strong></p>
                    <p class="warning">ADVERTENCIA: esta operación elimina permanentemente todos los datos.</p>
                </div>
                <div class="form-group"><label>Escribe "ELIMINAR" para confirmar:</label>
                    <input type="text" id="deleteConfirmation" placeholder="ELIMINAR">
                </div>`;
        }
        diskModal.dataset.operation = operation;
        diskModal.style.display = 'flex';
    }

    async function confirmPartitionOperation() {
        const op = diskModal.dataset.operation;
        const payload = { operation: op };

        if (op === 'create') {
            const size = parseFloat(document.getElementById('partitionSize')?.value);
            const fs   = document.getElementById('fileSystem')?.value;
            const lbl  = document.getElementById('partitionLabel')?.value || '';
            const ltr  = document.getElementById('partitionLetter')?.value || '';
            if (!size || size <= 0) { showResult('Validación', 'Tamaño no válido.', true); return; }
            payload.disk_id = currentDiskId;
            payload.size = size;
            payload.filesystem = fs;
            if (lbl) payload.label  = lbl;
            if (ltr) payload.letter = ltr;
        } else if (op === 'format') {
            const fs  = document.getElementById('formatFileSystem')?.value;
            const lbl = document.getElementById('formatLabel')?.value || '';
            payload.partition_id = currentPartId;
            payload.filesystem = fs;
            if (lbl) payload.label = lbl;
        } else if (op === 'delete') {
            const conf = (document.getElementById('deleteConfirmation')?.value || '').trim().toUpperCase();
            if (conf !== 'ELIMINAR') { showResult('Validación', 'Escribe "ELIMINAR" para confirmar.', true); return; }
            payload.partition_id = currentPartId;
        }

        diskModal.style.display = 'none';
        showResult('Procesando…', 'Ejecutando operación, espera por favor…', false);

        try {
            const r = await api('POST', '/api/particiones/partition_operation', payload);
            showResult('Resultado', r.output || 'Operación completada.', false);
            // Refrescar
            await loadDisks();
            if (currentDiskId) await loadPartitions(currentDiskId);
        } catch (e) {
            showResult('Error', e.message || 'Operación fallida', true);
        }
    }

    // ── Listeners ────────────────────────────────────────────────────
    if (refreshDisksBtn) refreshDisksBtn.addEventListener('click', loadDisks);
    if (createPartBtn)   createPartBtn.addEventListener('click', () => openPartitionModal('create'));
    if (formatPartBtn)   formatPartBtn.addEventListener('click', () => openPartitionModal('format'));
    if (deletePartBtn)   deletePartBtn.addEventListener('click', () => openPartitionModal('delete'));
    if (cancelOpBtn)     cancelOpBtn.addEventListener('click', () => { if (diskModal) diskModal.style.display = 'none'; });
    if (confirmOpBtn)    confirmOpBtn.addEventListener('click', confirmPartitionOperation);
    if (closeDiskModalBtn) closeDiskModalBtn.addEventListener('click', () => { if (diskModal) diskModal.style.display = 'none'; });
    if (closeCmdModalBtn)  closeCmdModalBtn.addEventListener('click', () => { if (commandModal) commandModal.style.display = 'none'; });

    // Click delegado en lista de discos
    if (disksList) disksList.addEventListener('click', function (ev) {
        const item = ev.target.closest('.disk-item');
        if (item && item.dataset.diskId) selectDisk(item.dataset.diskId);
    });
    // Click delegado en filas de particiones
    if (partitionsBody) partitionsBody.addEventListener('click', function (ev) {
        const tr = ev.target.closest('tr');
        if (tr && tr.dataset.partition) selectPartition(tr.dataset.partition);
    });
    // Click delegado en bloques visuales
    if (partitionsVisual) partitionsVisual.addEventListener('click', function (ev) {
        const block = ev.target.closest('.partition-block');
        if (block && block.dataset.partition) selectPartition(block.dataset.partition);
    });

    // Botón "Actualizar ahora" del footer
    const refreshBtn = document.getElementById('refreshBtn');
    if (refreshBtn) refreshBtn.addEventListener('click', loadDisks);

    // Cambio de máquina → reset y recarga
    window.addEventListener('machineChanged', function () {
        currentDiskId = null;
        currentPartId = null;
        partitionsData = [];
        loadDisks();
    });

    // Refresco periódico cada 30 s mientras la pestaña esté visible
    setInterval(() => {
        if (document.visibilityState === 'visible' && currentDiskId) {
            loadDiskDetail(currentDiskId);
            loadPartitions(currentDiskId);
        }
    }, 30000);

    // Init
    loadDisks();
});
