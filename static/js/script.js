document.addEventListener('DOMContentLoaded', function() {
    // Elementos del DOM
    const statusIndicator = document.getElementById('status-indicator');
    const modal = document.getElementById('commandModal');
    const modalTitle = document.getElementById('modalTitle');
    const commandOutput = document.getElementById('commandOutput');
    const commandInput = document.getElementById('commandInput');
    const executeCommandBtn = document.getElementById('executeCommand');

    // Estado de la conexión — la máquina se gestiona por window.MS
    let isConnected = true;

    // Alias para compatibilidad interna
    function machineQuery(sep) {
        return window.MS ? window.MS.machineQuery(sep) : '';
    }

    // Recargar datos cuando el usuario cambie de máquina
    window.addEventListener('machineChanged', function() {
        fetchSystemStats();
        refreshProcesses();
    });

    // Cerrar modal de comandos
    const _cmdInput = document.querySelector('.command-input');
    function closeCommandModal() {
        modal.style.display = 'none';
        if (_cmdInput) _cmdInput.style.display = '';
        const _ctrls = document.getElementById('modalControls');
        if (_ctrls) _ctrls.style.display = 'none';
        currentAction = null;
    }
    document.querySelectorAll('.close-button').forEach(btn => {
        btn.addEventListener('click', function() {
            const modalId = this.dataset.modal;
            if (modalId === 'commandModal' || !modalId) closeCommandModal();
            else if (modalId) document.getElementById(modalId).style.display = 'none';
        });
    });
    window.addEventListener('click', function(event) {
        if (event.target === modal) closeCommandModal();
    });

    // Comprobar conexión inicial
    checkConnection();
    
    // Función para comprobar la conexión
    function checkConnection() {
        fetch('/health')
            .then(response => {
                if (response.ok) {
                    return response.json();
                } else {
                    throw new Error('Error en la respuesta del servidor');
                }
            })
            .then(data => {
                if (data.status === 'ok') {
                    setConnected(true);
                    // Después de verificar la conexión, cargamos los datos iniciales
                    fetchSystemStats();
                } else {
                    setConnected(false);
                    console.error('Servidor no disponible:', data.message);
                }
            })
            .catch(error => {
                console.error('Error de conexión:', error);
                setConnected(false);
            });
    }
    
    // Función para actualizar indicador de estado.
    // status indica si el BACKEND Flask responde. El estado de la máquina remota
    // se actualiza desde updateCPUStats al recibir data.reachable.
    function setConnected(status) {
        isConnected = status;
        if (statusIndicator) {
            statusIndicator.className = isConnected ? 'status connected' : 'status disconnected';
            statusIndicator.textContent = isConnected ? 'CONECTADO' : 'DESCONECTADO';
        }
        // Si el backend cae, sidebar=offline. Si el backend está OK, sidebar=unknown
        // hasta que llegue la primera respuesta del PS con reachable=true/false.
        if (window.MS_updateSidebarStatus) {
            window.MS_updateSidebarStatus(isConnected ? 'unknown' : 'offline');
        }
    }
    
    // Datos para los gráficos
    function _nowLabel() {
        return new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }
    const _labelHistory = Array(15).fill('');

    // Datos para el gráfico de CPU
    const cpuData = {
        labels: _labelHistory,
        datasets: [{
            label: 'Uso de CPU (%)',
            data: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            borderColor: '#0078d7',
            backgroundColor: 'rgba(0, 120, 215, 0.1)',
            tension: 0.4,
            fill: true
        }]
    };

    // Datos para el gráfico de memoria
    const memoryData = {
        labels: _labelHistory,
        datasets: [{
            label: 'Uso de Memoria (%)',
            data: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            borderColor: '#0078d7',
            backgroundColor: 'rgba(0, 120, 215, 0.1)',
            tension: 0.4,
            fill: true
        }]
    };

    // Datos para el gráfico de disco
    const diskData = {
        labels: ['Usado', 'Libre'],
        datasets: [{
            data: [0, 100],
            backgroundColor: ['#0078d7', '#d0d0d0'],
            borderWidth: 0,
        }]
    };

    // Configuración común para los gráficos de línea
    const lineChartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                display: false
            },
            tooltip: {
                mode: 'index',
                intersect: false
            }
        },
        scales: {
            y: {
                beginAtZero: true,
                max: 100,
                ticks: {
                    stepSize: 25
                }
            },
            x: {
                display: false
            }
        },
        elements: {
            point: {
                radius: 0
            }
        }
    };

    // Configuración para el gráfico circular
    const doughnutChartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '70%',
        events: [],  // desactivar interactividad: sin tooltip ni hover-box
        plugins: {
            tooltip: { enabled: false },
            legend: {
                display: false
            }
        }
    };

    // Inicializar gráficos
    const cpuChart = new Chart(
        document.getElementById('cpuChart'),
        {
            type: 'line',
            data: cpuData,
            options: lineChartOptions
        }
    );

    const memoryChart = new Chart(
        document.getElementById('memoryChart'),
        {
            type: 'line',
            data: memoryData,
            options: lineChartOptions
        }
    );

    const diskChart = new Chart(
        document.getElementById('diskChart'),
        {
            type: 'doughnut',
            data: diskData,
            options: doughnutChartOptions
        }
    );

    // Usar el botón de actualización de procesos del HTML
    document.getElementById('refreshProcessBtn')?.addEventListener('click', () => refreshProcesses());

    // Botón de actualización global en el footer
    document.getElementById('refreshBtn')?.addEventListener('click', () => {
        fetchSystemStats();
        refreshProcesses();
    });

    // Actualizar las cabeceras de la tabla para mostrar el orden correcto
    const tableHeaders = document.querySelector('.process-table thead tr');
    if (tableHeaders) {
        tableHeaders.innerHTML = `
            <th>Nombre</th>
            <th>CPU %</th>
            <th>Memoria</th>
            <th>ID</th>
            <th class="proc-act-col">Acción</th>
        `;
    }

    // Solo superadmin/admin pueden matar procesos
    const _canKillProcess = ['superadmin', 'admin'].includes(
        (document.body.dataset.userRole || '').toLowerCase()
    );

    function killProcess(pid, btn) {
        if (!pid) return;
        if (!confirm(`¿Matar el proceso con PID ${pid}?`)) return;
        if (btn) { btn.disabled = true; btn.classList.add('loading'); }
        fetch('/api/rendimiento/process/kill' + machineQuery('?'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pid: pid })
        })
            .then(r => r.json().then(data => ({ ok: r.ok, data })))
            .then(({ ok, data }) => {
                if (!ok || data.error) {
                    alert('Error al matar el proceso: ' + (data.error || 'desconocido'));
                    return;
                }
                refreshProcesses();
            })
            .catch(err => {
                alert('Error al matar el proceso: ' + err.message);
            })
            .finally(() => {
                if (btn) { btn.disabled = false; btn.classList.remove('loading'); }
            });
    }

    // Delegación de eventos para los botones de matar proceso
    document.querySelector('.process-table tbody')?.addEventListener('click', (ev) => {
        const btn = ev.target.closest('.proc-kill-btn');
        if (!btn) return;
        killProcess(btn.dataset.pid, btn);
    });

    // Función para obtener datos del sistema
    function fetchSystemStats() {
        if (!isConnected) return;

        const url = '/api/system' + machineQuery('?');
        fetch(url)
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    // Error de la máquina remota — no desconectar la app
                    console.warn('Error de máquina:', data.error);
                    showMachineError();
                    return;
                }
                updateCPUStats(data.cpu);
                updateMemoryStats(data.memory);
                fetchDiskList();
                fetchNetworkStats();
                const now = new Date();
                const ts = now.toLocaleDateString('es-ES') + ' ' +
                    String(now.getHours()).padStart(2,'0') + ':' +
                    String(now.getMinutes()).padStart(2,'0') + ':' +
                    String(now.getSeconds()).padStart(2,'0');
                const lu = document.getElementById('lastUpdate');
                if (lu) lu.textContent = ts;
                // Actualizar dot con la accesibilidad reportada por el backend
                if (data.machine && window.MS) {
                    const status = data.machine.reachable ? 'online' : 'offline';
                    window.MS.updateDot(status);
                    const opt = document.querySelector(`#machineSelect option[value="${data.machine.id}"]`);
                    if (opt) opt.dataset.status = status;
                }
            })
            .catch(error => {
                console.error('Error al obtener datos del sistema:', error);
                setConnected(false);
            });
    }

    function showMachineError() {
        updateCPUStats({value: 0, history: Array(15).fill(0)});
        updateMemoryStats({value: 0, history: Array(15).fill(0)});
        updateDiskStats({used: 0, free: 100});
        if (window.MS) window.MS.updateDot('offline');
    }

    // ─── Discos: lista, selector y agregados ────────────────────────────────
    let allDisks = [];
    let diskTotals = null;
    let selectedDisk = 'all';

    function fmtGB(gb) {
        if (gb == null) return '--';
        if (gb >= 1024) return `${(gb/1024).toLocaleString('es-ES', { maximumFractionDigits: 1 })} TB`;
        if (gb >= 1)    return `${gb.toLocaleString('es-ES', { maximumFractionDigits: 0 })} GB`;
        return `${(gb*1024).toLocaleString('es-ES', { maximumFractionDigits: 0 })} MB`;
    }

    function renderDiskInfo() {
        if (!diskTotals) return;
        const view = (selectedDisk === 'all')
            ? diskTotals
            : (allDisks.find(x => x.letter === selectedDisk) || diskTotals);

        // Donut + textos centrales — reflejan el disco seleccionado
        if (typeof diskChart !== 'undefined' && diskChart) {
            diskChart.data.datasets[0].data = [view.used_pct, Math.max(0, 100 - view.used_pct)];
            diskChart.update();
        }
        const pctEl  = document.querySelector('.disk-percent');
        const textEl = document.querySelector('.disk-text');
        if (pctEl)  pctEl.textContent  = `${view.used_pct.toFixed(2)}%`;
        if (textEl) textEl.textContent = `${fmtGB(view.free_gb)} libre`;

        // Tarjeta superior — capacidad TOTAL sumada de todos los discos
        const diskValEl = document.getElementById('diskValue');
        const diskSubEl = document.getElementById('diskSub');
        if (diskValEl) diskValEl.textContent = fmtGB(diskTotals.total_gb);
        if (diskSubEl) diskSubEl.textContent = `${fmtGB(diskTotals.used_gb)} usados · ${fmtGB(diskTotals.free_gb)} libres`;

        // Lista clicable: "Todos los discos" + cada unidad
        const drives = document.getElementById('diskDrives');
        if (!drives) return;
        if (allDisks.length === 0) {
            drives.innerHTML = '<div class="drive"><p class="drive-text">Sin discos detectados</p></div>';
            return;
        }

        const items = [
            {
                key: 'all',
                label: `Todos los discos (${fmtGB(diskTotals.total_gb)})`,
                pct: diskTotals.used_pct,
            },
            ...allDisks.map(d => ({
                key: d.letter,
                label: `${d.letter} ${d.label} (${fmtGB(d.total_gb)})`,
                pct: d.used_pct,
            })),
        ];

        drives.innerHTML = items.map(it => `
            <div class="drive${it.key === selectedDisk ? ' selected' : ''}" data-disk="${it.key}">
                <p class="drive-text">${it.label}</p>
                <div class="progress-bar">
                    <div class="progress" style="width: ${it.pct}%"></div>
                </div>
            </div>
        `).join('');

        // Wire up clicks
        drives.querySelectorAll('.drive[data-disk]').forEach(el => {
            el.addEventListener('click', () => {
                selectedDisk = el.dataset.disk;
                renderDiskInfo();
            });
        });
    }

    function fetchDiskList() {
        if (!isConnected) return;
        fetch('/api/rendimiento/disk_list' + machineQuery('?'))
            .then(r => r.ok ? r.json() : null)
            .then(data => {
                if (!data) return;
                allDisks = data.disks || [];
                diskTotals = data.totals || null;
                // Si el disco seleccionado ya no existe, volver a "Todos"
                if (selectedDisk !== 'all' && !allDisks.some(d => d.letter === selectedDisk)) {
                    selectedDisk = 'all';
                }
                renderDiskInfo();
            })
            .catch(() => {});
    }

    // Cargar estadísticas de red (tarjeta "Red")
    function fmtBps(bps) {
        if (!bps || bps < 1) return '0 bps';
        if (bps >= 1e9) return `${(bps/1e9).toLocaleString('es-ES', { maximumFractionDigits: 1 })} Gbps`;
        if (bps >= 1e6) return `${(bps/1e6).toLocaleString('es-ES', { maximumFractionDigits: 1 })} Mbps`;
        if (bps >= 1e3) return `${(bps/1e3).toLocaleString('es-ES', { maximumFractionDigits: 0 })} Kbps`;
        return `${Math.round(bps)} bps`;
    }

    function fetchNetworkStats() {
        if (!isConnected) return;
        fetch('/api/rendimiento/network_stats' + machineQuery('?'))
            .then(r => r.ok ? r.json() : null)
            .then(data => {
                if (!data) return;
                const down = Number(data.down_bps) || 0;
                const up   = Number(data.up_bps)   || 0;
                const total = down + up;
                const el  = document.getElementById('netValue');
                const sub = document.getElementById('netSub');
                if (el)  el.textContent  = fmtBps(total);
                if (sub) sub.textContent = `↓ ${fmtBps(down)}  ·  ↑ ${fmtBps(up)}`;
            })
            .catch(() => {});
    }
    
    // Función para obtener y actualizar solo la lista de procesos
    function refreshProcesses() {
        if (!isConnected) return;

        const tableBody = document.querySelector('.process-table tbody');
        tableBody.innerHTML = '<tr><td colspan="5">Cargando procesos...</td></tr>';

        fetch('/api/rendimiento/processes' + machineQuery('?'))
            .then(response => {
                if (!response.ok) throw new Error('Error en la respuesta del servidor');
                return response.json();
            })
            .then(data => {
                updateProcessTable(data);
            })
            .catch(error => {
                console.error('Error al obtener procesos:', error);
                tableBody.innerHTML = '<tr><td colspan="5">Error al cargar procesos</td></tr>';
            });
    }
    
    // History local (rolling window). En la PRIMERA carga lo seedeamos con el
    // `history` de la BD que envía el servidor: así el gráfico arranca con los
    // últimos 15 minutos reales en vez de ceros. Después, cada refresh empuja
    // el nuevo `value` y descarta el más viejo → la curva se anima en directo.
    let _cpuHistory = Array(15).fill(0);
    let _memHistory = Array(15).fill(0);
    let _cpuSeeded  = false;
    let _memSeeded  = false;

    function _seedOrRoll(history, seeded, serverHist, liveVal) {
        if (!seeded && Array.isArray(serverHist) && serverHist.length === 15) {
            return { hist: serverHist.slice(), seeded: true };
        }
        history.shift();
        history.push(liveVal);
        return { hist: history, seeded: seeded };
    }

    function _updateLabels(seededNow) {
        const now = new Date();
        if (seededNow) {
            // Genera 15 timestamps reales hacia atrás desde ahora (intervalo 3 s)
            for (let i = 0; i < 15; i++) {
                const t = new Date(now - (14 - i) * 3000);
                _labelHistory[i] = t.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            }
        } else {
            _labelHistory.shift();
            _labelHistory.push(_nowLabel());
        }
        cpuChart.data.labels    = [..._labelHistory];
        memoryChart.data.labels = [..._labelHistory];
    }

    function updateCPUStats(data) {
        if (!data) return;
        if (data.reachable === false && window.MS_updateSidebarStatus) {
            window.MS_updateSidebarStatus('offline');
        } else if (data.reachable === true && window.MS_updateSidebarStatus) {
            window.MS_updateSidebarStatus('online');
        }
        const cpuUsage = data.value || 0;
        const wasSeededBefore = _cpuSeeded;
        const r = _seedOrRoll(_cpuHistory, _cpuSeeded, data.history, cpuUsage);
        _cpuHistory = r.hist; _cpuSeeded = r.seeded;
        _updateLabels(!wasSeededBefore && r.seeded);
        cpuChart.data.datasets[0].data = [..._cpuHistory];
        cpuChart.update();
        const el = document.getElementById('cpuValue');
        if (el) el.textContent = `${cpuUsage.toFixed(1)}%`;
        const sub = document.getElementById('cpuSub');
        if (sub) sub.textContent = 'Uso del procesador';
    }

    function updateMemoryStats(data) {
        if (!data) return;
        const memoryUsage = data.value || 0;
        const r = _seedOrRoll(_memHistory, _memSeeded, data.history, memoryUsage);
        _memHistory = r.hist; _memSeeded = r.seeded;
        memoryChart.data.datasets[0].data = [..._memHistory];
        memoryChart.update();
        const el = document.getElementById('memValue');
        if (el) el.textContent = `${memoryUsage.toFixed(1)}%`;
        const sub = document.getElementById('memSub');
        if (sub) sub.textContent = 'Uso de memoria RAM';
    }

    // Cuando se cambia de máquina, el history actual deja de ser válido —
    // reseteamos para que la próxima respuesta sea tratada como "seed inicial".
    window.addEventListener('machineChanged', () => {
        _cpuSeeded = false; _memSeeded = false;
        _cpuHistory = Array(15).fill(0);
        _memHistory = Array(15).fill(0);
        _labelHistory.fill('');
    });
    
    // Función para actualizar estadísticas de disco (modificada para mostrar 2 decimales)
    function updateDiskStats(data) {
        if (!data) return;
        
        // Actualizar el gráfico de disco
        diskChart.data.datasets[0].data = [data.used, data.free];
        diskChart.update();
        
        // Formatear números con exactamente 2 decimales
        const formattedUsed = Number(data.used).toFixed(2);
        const formattedFree = Number(data.free).toFixed(2);
        
        // Actualizar el texto
        document.querySelector('.disk-percent').textContent = `${formattedUsed}%`;
        document.querySelector('.disk-text').textContent = `${formattedFree}% Libre`;
        
        // Actualizar tarjeta de disco
        const diskEl = document.getElementById('diskValue');
        if (diskEl) diskEl.textContent = `${data.used}%`;
        const diskSub = document.getElementById('diskSub');
        if (diskSub) diskSub.textContent = `${data.free !== undefined ? data.free : ''}% libre`;
        // Actualizar barras de las unidades si existen
        const drive0 = document.querySelectorAll('.drive')[0];
        if (drive0) {
            const prog = drive0.querySelector('.progress');
            if (prog) prog.style.width = `${data.used}%`;
            const dt = drive0.querySelector('.drive-text');
            if (dt) dt.textContent = `C: - Sistema (${data.used}%)`;
        }
    }
    
    // Devuelve el HTML del botón de matar proceso (vacío si el usuario no tiene permisos)
    function _killBtnHTML(pid) {
        if (!_canKillProcess || !pid || pid === 'N/A') return '';
        const safePid = String(pid).replace(/[^0-9]/g, '');
        if (!safePid) return '';
        return `<button class="proc-kill-btn" data-pid="${safePid}" title="Matar proceso (PID ${safePid})" aria-label="Matar proceso ${safePid}">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>`;
    }

    // Función para actualizar la tabla de procesos
    function updateProcessTable(processData) {
        const tableBody = document.querySelector('.process-table tbody');
        tableBody.innerHTML = ''; // Limpiar tabla existente
        
        // Para procesar la respuesta directa en formato de texto del servidor
        if (typeof processData === 'string') {
            const lines = processData.split('\n');
            let headerFound = false;
            
            for (let i = 0; i < lines.length; i++) {
                const line = lines[i].trim();
                
                // Buscar la línea de encabezado
                if (line.includes('Name') && line.includes('Id') && line.includes('CPU')) {
                    headerFound = true;
                    continue;
                }
                
                // Procesar las líneas de datos después del encabezado
                if (headerFound && line) {
                    // Buscar posiciones de columnas basadas en el encabezado
                    const nameEndIdx = line.indexOf(' ', 20);
                    const idEndIdx = nameEndIdx + 8; // Aproximadamente 8 espacios para el ID
                    
                    if (nameEndIdx > 0) {
                        const name = line.substring(0, nameEndIdx).trim();
                        const pid = line.substring(nameEndIdx, idEndIdx).trim();
                        const cpu = line.substring(idEndIdx).trim();

                        // Calcular un valor de memoria simulado basado en el PID
                        // En un entorno real, esto debería venir del servidor
                        const memoryMB = Math.floor(Math.random() * 500) + 10;

                        const row = document.createElement('tr');
                        row.innerHTML = `
                            <td>${name}</td>
                            <td>${cpu}%</td>
                            <td>${memoryMB} MB</td>
                            <td>${pid}</td>
                            <td class="proc-act-col">${_killBtnHTML(pid)}</td>
                        `;
                        tableBody.appendChild(row);
                    }
                }
            }
        } 
        // La versión original para procesar un array de objetos
        else if (Array.isArray(processData)) {
            const fmtMem = (n) => {
                // Estilo Administrador de Tareas: separador de miles "." y decimal ","
                // Bajo 100 MB: 1 decimal (ej: "12,3 MB"); >= 100 MB: sin decimales (ej: "1.558 MB")
                if (n >= 100) {
                    return `${n.toLocaleString('es-ES', { maximumFractionDigits: 0 })} MB`;
                }
                return `${n.toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} MB`;
            };
            const fmtCpu = (n) => `${n.toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;

            processData.forEach(process => {
                const row = document.createElement('tr');

                const name = process.name || 'N/A';
                const cpuNum = typeof process.cpu === 'number' ? process.cpu : parseFloat(process.cpu);
                const cpu = isNaN(cpuNum) ? (process.cpu || '0,0%') : fmtCpu(cpuNum);

                let memory = 'N/A';
                if (process.memory != null && process.memory !== 'N/A') {
                    const s = String(process.memory).trim().replace(/\s*MB\s*$/i, '');
                    const num = parseFloat(s);
                    memory = isNaN(num) ? String(process.memory) : fmtMem(num);
                }
                const pid = process.pid || 'N/A';

                row.innerHTML = `
                    <td>${name}</td>
                    <td>${cpu}</td>
                    <td>${memory}</td>
                    <td>${pid}</td>
                    <td class="proc-act-col">${_killBtnHTML(pid)}</td>
                `;
                tableBody.appendChild(row);
            });
        }
    }
    
    // Cargar procesos inicialmente
    refreshProcesses();
    
    // Actualización periódica: 4 primeras veces cada 3 s, luego cada 10 s
    let _pollCount = 0;
    function _schedulePoll() {
        const delay = _pollCount < 4 ? 3000 : 10000;
        setTimeout(() => {
            if (isConnected) {
                fetchSystemStats();
            } else {
                checkConnection();
            }
            _pollCount++;
            _schedulePoll();
        }, delay);
    }
    _schedulePoll();

    // Manejar los botones de acción rápida
    const commandInputDiv = document.querySelector('.command-input');
    const modalControls   = document.getElementById('modalControls');
    const modalCountSelect= document.getElementById('modalCountSelect');
    let currentAction = null;

    function runActionFetch(action, count) {
        commandOutput.textContent = 'Ejecutando...';
        const mq = (window.MS && window.MS.machineQuery) ? window.MS.machineQuery('&') : '';
        const cnt = count ? `&count=${encodeURIComponent(count)}` : '';
        fetch(`/procesos?action=${encodeURIComponent(action)}${cnt}${mq}`)
            .then(r => { if (!r.ok) throw new Error(`Error ${r.status}`); return r.json(); })
            .then(data => { commandOutput.textContent = data.output || data.error || 'Comando ejecutado correctamente'; })
            .catch(err => { commandOutput.textContent = `Error: ${err.message}`; });
    }

    function setupCountSelector(action) {
        if (action === 'log' || action === 'servicios') {
            // Reset opciones base 10/20/50 y añadir "Todos" solo para servicios
            modalCountSelect.innerHTML =
                '<option value="10">10</option>' +
                '<option value="20">20</option>' +
                '<option value="50">50</option>' +
                (action === 'servicios' ? '<option value="all">Todos</option>' : '');
            modalCountSelect.value = '10';
            modalControls.style.display = 'flex';
        } else {
            modalControls.style.display = 'none';
        }
    }

    modalCountSelect?.addEventListener('change', () => {
        if (currentAction) runActionFetch(currentAction, modalCountSelect.value);
    });

    // ── Confirmación reinicio ─────────────────────────────────────────
    (function () {
        const restartModal  = document.getElementById('restartConfirmModal');
        const confirmInput  = document.getElementById('restartConfirmInput');
        const doBtn         = document.getElementById('restartDoBtn');
        const cancelBtn     = document.getElementById('restartCancelBtn');
        const closeBtn      = document.getElementById('restartModalClose');
        const resultDiv     = document.getElementById('restartResult');
        if (!restartModal) return;

        function openRestartModal() {
            confirmInput.value = '';
            doBtn.disabled = true;
            doBtn.style.opacity = '0.45';
            doBtn.style.cursor = 'not-allowed';
            resultDiv.style.display = 'none';
            restartModal.style.display = 'block';
            setTimeout(() => confirmInput.focus(), 80);
        }

        function closeRestartModal() {
            restartModal.style.display = 'none';
        }

        confirmInput.addEventListener('input', function () {
            const ok = this.value === 'CONFIRMAR';
            doBtn.disabled = !ok;
            doBtn.style.opacity = ok ? '1' : '0.45';
            doBtn.style.cursor = ok ? 'pointer' : 'not-allowed';
        });

        cancelBtn.addEventListener('click', closeRestartModal);
        closeBtn.addEventListener('click', closeRestartModal);
        restartModal.addEventListener('click', function (e) {
            if (e.target === restartModal) closeRestartModal();
        });

        doBtn.addEventListener('click', function () {
            if (confirmInput.value !== 'CONFIRMAR') return;
            doBtn.disabled = true;
            doBtn.textContent = 'Reiniciando…';
            resultDiv.style.display = 'none';

            const mq = (window.MS && window.MS.machineQuery) ? window.MS.machineQuery('&') : '';
            const machineId = mq ? new URLSearchParams(mq.replace(/^&/, '')).get('machine_id') : null;
            const csrfMeta = document.querySelector('meta[name="csrf-token"]');
            const csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : '';

            fetch('/api/restart', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify({ confirm: 'CONFIRMAR', machine_id: machineId })
            })
            .then(r => r.json())
            .then(data => {
                const ok = data.output && !data.output.toLowerCase().includes('error');
                resultDiv.style.display = 'block';
                resultDiv.style.background = ok ? 'rgba(39,174,96,0.12)' : 'rgba(192,57,43,0.12)';
                resultDiv.style.border = ok ? '1px solid #27ae60' : '1px solid #c0392b';
                resultDiv.style.color = ok ? '#2ecc71' : '#e74c3c';
                resultDiv.textContent = data.output || data.error || 'Comando enviado.';
                doBtn.textContent = 'Reiniciar ahora';
            })
            .catch(() => {
                resultDiv.style.display = 'block';
                resultDiv.style.background = 'rgba(192,57,43,0.12)';
                resultDiv.style.border = '1px solid #c0392b';
                resultDiv.style.color = '#e74c3c';
                resultDiv.textContent = 'Error de red al enviar el comando.';
                doBtn.textContent = 'Reiniciar ahora';
                doBtn.disabled = false;
                doBtn.style.opacity = '1';
            });
        });

        // Exponer para que el handler genérico lo use
        window._openRestartModal = openRestartModal;
    })();

    document.querySelectorAll('.action-btn').forEach(button => {
        button.addEventListener('click', function() {
            const action = this.getAttribute('data-action');
            const title  = this.getAttribute('data-title') || this.textContent.trim();

            if (!isConnected) {
                alert('No hay conexión con el servidor. Intente nuevamente más tarde.');
                return;
            }

            if (action === 'restart') {
                if (window._openRestartModal) window._openRestartModal();
                return;
            }

            currentAction = action;
            modalTitle.textContent = title;
            if (commandInputDiv) commandInputDiv.style.display = 'none';
            setupCountSelector(action);
            modal.style.display = 'block';

            const initialCount = (action === 'log' || action === 'servicios') ? '10' : '';
            runActionFetch(action, initialCount);
        });
    });
    
    // Manejar los items del menú
    document.querySelectorAll('.nav-menu li').forEach(item => {
        item.addEventListener('click', function(e) {
            // Obtener el enlace dentro del elemento de lista
            const link = this.querySelector('a');
            const href = link.getAttribute('href');
            
            // Si el enlace tiene un href real (no solo "#")
            if (href && href !== '#') {
                // Permitir el comportamiento normal del enlace
                return;
            }
            
            // Para otros enlaces (como "#"), prevenir el comportamiento predeterminado
            e.preventDefault();
            document.querySelector('.nav-menu li.active').classList.remove('active');
            this.classList.add('active');
            // Se podria cargar contenido especifico
        });
    });
    
    // Ejecutar comando ingresado manualmente
    executeCommandBtn.addEventListener('click', function() {
        const command = commandInput.value.trim();
        
        if (!command) return;
        
        commandOutput.textContent = 'Ejecutando comando...';
        
        // Usar el nuevo endpoint de API para ejecutar comandos
        fetch('/api/command', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ command: command, machine_id: currentMachineId })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`Error ${response.status}: ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            commandOutput.textContent = data.output || 'Comando ejecutado correctamente';
        })
        .catch(error => {
            console.error('Error al ejecutar comando:', error);
            commandOutput.textContent = `Error: ${error.message}`;
        });
        
        // Limpiar el input
        commandInput.value = '';
    });
    
    // También permitir enviar con Enter
    commandInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            executeCommandBtn.click();
        }
    });
});