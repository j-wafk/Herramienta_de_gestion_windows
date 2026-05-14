// machine_selector.js — Selector de máquina compartido entre todas las páginas.
// Persiste la selección en localStorage (clave: ms_machine_id).
// Expone window.MS con: getMachineId(), machineQuery(sep), reload().
// Dispara el evento CustomEvent 'machineChanged' en window al cambiar.

(function () {
    'use strict';

    var _machineId = localStorage.getItem('ms_machine_id') || null;

    // ── CSS inline ────────────────────────────────────────────────
    var CSS = [
        '.ms-host{display:flex;align-items:center;gap:8px;}',
        '#machineSelect{padding:4px 8px;border-radius:4px;border:1px solid rgba(255,255,255,.4);',
            'background:rgba(255,255,255,.15);color:#fff;font-size:13px;max-width:220px;}',
        '#machineSelect option{background:#1e293b;color:#fff;}',
        '.ms-dot{width:10px;height:10px;border-radius:50%;background:#94a3b8;flex-shrink:0;}',
        '.ms-dot.online{background:#22c55e;box-shadow:0 0 5px #22c55e;}',
        '.ms-dot.offline{background:#ef4444;box-shadow:0 0 5px #ef4444;}',
        '.ms-dot.unknown{background:#94a3b8;}',
        '.ms-manage-btn{background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.3);',
            'color:#fff;border-radius:4px;padding:3px 8px;cursor:pointer;font-size:15px;line-height:1;}',
        '.ms-manage-btn:hover{background:rgba(255,255,255,.28);}',
        // modal
        '.ms-modal{display:none;position:fixed;top:0;left:0;width:100%;height:100%;',
            'background:rgba(0,0,0,.5);z-index:9999;align-items:center;justify-content:center;}',
        '.ms-modal.open{display:flex;}',
        '.ms-modal-box{background:#fff;border-radius:10px;padding:24px;min-width:380px;max-width:480px;',
            'width:90%;position:relative;box-shadow:0 8px 32px rgba(0,0,0,.2);}',
        '.ms-modal-box h3{margin:0 0 16px;font-size:16px;color:#1e293b;}',
        '.ms-close{position:absolute;top:12px;right:14px;background:none;border:none;font-size:20px;',
            'cursor:pointer;color:#64748b;}',
        '.ms-close:hover{color:#1e293b;}',
        '.ms-list{display:flex;flex-direction:column;gap:6px;margin-bottom:16px;}',
        '.ms-item{display:flex;align-items:center;gap:8px;padding:8px;border:1px solid #e2e8f0;',
            'border-radius:6px;font-size:13px;}',
        '.ms-item .ms-name{flex:1;font-weight:500;color:#1e293b;}',
        '.ms-item .ms-addr{color:#64748b;font-size:12px;}',
        '.ms-ping-btn,.ms-del-btn{padding:3px 8px;border-radius:4px;border:1px solid #e2e8f0;',
            'font-size:12px;cursor:pointer;}',
        '.ms-ping-btn{background:#dbeafe;color:#1d4ed8;border-color:#bfdbfe;}',
        '.ms-ping-btn:hover{background:#bfdbfe;}',
        '.ms-del-btn{background:#fee2e2;color:#dc2626;border-color:#fecaca;}',
        '.ms-del-btn:hover{background:#fecaca;}',
        'hr.ms-hr{border:none;border-top:1px solid #e2e8f0;margin:12px 0;}',
        '.ms-add-title{font-size:13px;font-weight:600;color:#374151;margin-bottom:8px;}',
        '.ms-add-row{display:flex;gap:6px;flex-wrap:wrap;}',
        '.ms-add-row input{flex:1;min-width:120px;padding:6px 8px;border:1px solid #e2e8f0;',
            'border-radius:4px;font-size:13px;}',
        '.ms-add-row input[type=number]{max-width:80px;}',
        '.ms-add-btn{padding:6px 12px;background:#2563eb;color:#fff;border:none;border-radius:4px;',
            'cursor:pointer;font-size:13px;}',
        '.ms-add-btn:hover{background:#1d4ed8;}',
        '.ms-empty{color:#94a3b8;font-size:13px;font-style:italic;padding:8px 0;}',
    ].join('');

    function injectCSS() {
        if (document.getElementById('ms-css')) return;
        var s = document.createElement('style');
        s.id = 'ms-css';
        s.textContent = CSS;
        document.head.appendChild(s);
    }

    // ── Modal ─────────────────────────────────────────────────────
    var _modal = null;

    function buildModal() {
        if (_modal) return _modal;
        _modal = document.createElement('div');
        _modal.id = 'ms-modal';
        _modal.className = 'ms-modal';
        _modal.innerHTML =
            '<div class="ms-modal-box">' +
                '<button class="ms-close" id="ms-close-btn">&times;</button>' +
                '<h3>Gestión de Máquinas</h3>' +
                '<div class="ms-list" id="ms-machines-list"><p class="ms-empty">Cargando...</p></div>' +
                '<hr class="ms-hr">' +
                '<p class="ms-add-title">Agregar máquina</p>' +
                '<div class="ms-add-row">' +
                    '<input type="text" id="ms-new-name" placeholder="Nombre (ej. Servidor-01)">' +
                    '<input type="text" id="ms-new-ip" placeholder="IP (ej. 192.168.1.50)">' +
                    '<input type="number" id="ms-new-port" placeholder="Puerto" value="12345">' +
                    '<button class="ms-add-btn" id="ms-add-btn">Agregar</button>' +
                '</div>' +
            '</div>';
        document.body.appendChild(_modal);

        document.getElementById('ms-close-btn').addEventListener('click', closeModal);
        _modal.addEventListener('click', function (e) { if (e.target === _modal) closeModal(); });
        document.getElementById('ms-add-btn').addEventListener('click', addMachine);
        return _modal;
    }

    function openModal() { buildModal(); _modal.classList.add('open'); loadMachines(); }
    function closeModal() { if (_modal) _modal.classList.remove('open'); }

    // ── Host injection ────────────────────────────────────────────
    function buildHost(host) {
        host.className = 'ms-host';
        host.innerHTML =
            '<select id="machineSelect" title="Seleccionar máquina"><option>Cargando...</option></select>' +
            '<button id="ms-manage" class="ms-manage-btn" title="Gestionar máquinas">+</button>';

        document.getElementById('machineSelect').addEventListener('change', onSelectChange);
        document.getElementById('ms-manage').addEventListener('click', openModal);
    }

    // ── Dot + conn-badge cabecera ────────────────────────────────
    function updateDot(status) {
        var dot = document.getElementById('machineStatus');
        if (dot) {
            dot.className = 'ms-dot ' + (status || 'unknown');
            dot.title = status === 'online' ? 'En línea' : status === 'offline' ? 'Sin conexión' : 'Estado desconocido';
        }
        updateConnBadge(status);
    }

    // Inyecta UNA sola vez una hoja de estilos que pinta el badge según una
    // data-status en `.conn-badge`. Usa `!important` para ganar a los atributos
    // fill/stroke inline del SVG (#38B000 hardcodeado en cada template).
    function ensureBadgeCSS() {
        if (document.getElementById('ms-badge-css')) return;
        var s = document.createElement('style');
        s.id = 'ms-badge-css';
        s.textContent = [
            '.conn-badge[data-status="online"]  svg, .conn-badge[data-status="online"]  svg * { fill: #38B000 !important; stroke: #38B000 !important; }',
            '.conn-badge[data-status="offline"] svg, .conn-badge[data-status="offline"] svg * { fill: #DC2626 !important; stroke: #DC2626 !important; }',
            '.conn-badge[data-status="warning"] svg, .conn-badge[data-status="warning"] svg * { fill: #F59E0B !important; stroke: #F59E0B !important; }',
            '.conn-badge[data-status="unknown"] svg, .conn-badge[data-status="unknown"] svg * { fill: #9CA3AF !important; stroke: #9CA3AF !important; }',
        ].join('\n');
        document.head.appendChild(s);
    }

    // Actualiza el badge "CONECTADO / DESCONECTADO" del header
    function updateConnBadge(status) {
        ensureBadgeCSS();
        var lbl   = document.getElementById('connLabel');
        var badge = document.querySelector('.conn-badge');
        var key   = (status === 'online' || status === 'offline' || status === 'warning') ? status : 'unknown';
        var text  = key === 'online'   ? 'CONECTADO'
                  : key === 'offline'  ? 'DESCONECTADO'
                  : key === 'warning'  ? 'AVISO'
                  : 'DESCONOCIDO';
        if (badge) badge.setAttribute('data-status', key);
        if (lbl)   lbl.textContent = text;
    }

    // ── Machines API ──────────────────────────────────────────────
    function loadMachines() {
        return fetch('/api/machines')
            .then(function (r) { return r.json(); })
            .then(function (machines) {
                populateSelect(machines);
                populateList(machines);
                return machines;
            })
            .catch(function (e) { console.warn('MS: error cargando máquinas:', e); });
    }

    function notifyListChanged() {
        try { window.dispatchEvent(new CustomEvent('machineListChanged')); } catch (_) {}
    }

    function populateSelect(machines) {
        var sel = document.getElementById('machineSelect');
        if (!sel) return;
        sel.innerHTML = '';
        machines.forEach(function (m) {
            var opt = document.createElement('option');
            opt.value = m.id;
            opt.textContent = m.name + ' (' + m.ip + ')';
            opt.dataset.status = m.status;
            sel.appendChild(opt);
        });

        var saved = localStorage.getItem('ms_machine_id');
        var valid = saved && machines.some(function (m) { return String(m.id) === saved; });
        if (valid) {
            _machineId = saved;
            sel.value = saved;
            var cur = machines.find(function (m) { return String(m.id) === saved; });
            if (cur) updateDot(cur.status);
        } else if (machines.length > 0) {
            _machineId = String(machines[0].id);
            sel.value = _machineId;
            localStorage.setItem('ms_machine_id', _machineId);
            updateDot(machines[0].status);
        }
    }

    function populateList(machines) {
        var listEl = document.getElementById('ms-machines-list');
        if (!listEl) return;
        if (machines.length === 0) {
            listEl.innerHTML = '<p class="ms-empty">No hay máquinas registradas.</p>';
            return;
        }
        listEl.innerHTML = '';
        machines.forEach(function (m) {
            var item = document.createElement('div');
            item.className = 'ms-item';
            item.innerHTML =
                '<span class="ms-dot ' + (m.status || 'unknown') + '"></span>' +
                '<span class="ms-name">' + m.name + '</span>' +
                '<span class="ms-addr">' + m.ip + ':' + m.port + '</span>' +
                '<button class="ms-ping-btn" data-id="' + m.id + '">Ping</button>' +
                '<button class="ms-del-btn" data-id="' + m.id + '">✕</button>';
            listEl.appendChild(item);
        });
        listEl.querySelectorAll('.ms-ping-btn').forEach(function (btn) {
            btn.addEventListener('click', function () { pingMachine(this.dataset.id, this); });
        });
        listEl.querySelectorAll('.ms-del-btn').forEach(function (btn) {
            btn.addEventListener('click', function () { deleteMachine(this.dataset.id); });
        });
    }

    function pingMachine(id, btn) {
        if (btn) { btn.textContent = '...'; btn.disabled = true; }
        fetch('/api/machines/' + id + '/ping', { method: 'POST' })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (btn) { btn.textContent = 'Ping'; btn.disabled = false; }
                var item = btn ? btn.closest('.ms-item') : null;
                if (item) item.querySelector('.ms-dot').className = 'ms-dot ' + data.status;
                if (String(id) === String(_machineId)) {
                    updateDot(data.status);
                    var opt = document.querySelector('#machineSelect option[value="' + id + '"]');
                    if (opt) opt.dataset.status = data.status;
                }
            })
            .catch(function () { if (btn) { btn.textContent = 'Ping'; btn.disabled = false; } });
    }

    function deleteMachine(id) {
        if (!confirm('¿Eliminar esta máquina y todos sus datos?')) return;
        fetch('/api/machines/' + id, { method: 'DELETE' })
            .then(function () {
                if (String(id) === String(_machineId)) {
                    _machineId = null;
                    localStorage.removeItem('ms_machine_id');
                }
                loadMachines();
                notifyListChanged();
            })
            .catch(function (e) { console.error('MS: error eliminando máquina:', e); });
    }

    function addMachine() {
        var name = (document.getElementById('ms-new-name') || {}).value || '';
        var ip   = (document.getElementById('ms-new-ip')   || {}).value || '';
        var port = parseInt((document.getElementById('ms-new-port') || {}).value) || 12345;
        name = name.trim(); ip = ip.trim();
        if (!name || !ip) { alert('Nombre e IP son obligatorios'); return; }
        fetch('/api/machines', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, ip: ip, port: port })
        })
        .then(function (r) { return r.json(); })
        .then(function () {
            document.getElementById('ms-new-name').value = '';
            document.getElementById('ms-new-ip').value   = '';
            document.getElementById('ms-new-port').value = '12345';
            loadMachines();
            notifyListChanged();
        })
        .catch(function (e) { console.error('MS: error agregando máquina:', e); });
    }

    // ── Select change ─────────────────────────────────────────────
    function onSelectChange() {
        var sel = document.getElementById('machineSelect');
        _machineId = sel ? (sel.value || null) : null;
        localStorage.setItem('ms_machine_id', _machineId || '');
        var opt = sel ? sel.options[sel.selectedIndex] : null;
        updateDot(opt ? opt.dataset.status : 'unknown');
        window.dispatchEvent(new CustomEvent('machineChanged', { detail: { machineId: _machineId } }));
    }

    // ── Init ──────────────────────────────────────────────────────
    function init() {
        injectCSS();
        var host = document.getElementById('machine-selector-host');
        if (host) buildHost(host);
        buildModal();   // build but don't open
        loadMachines();
    }

    document.addEventListener('DOMContentLoaded', init);

    // Actualiza el status registrado del <option> de una máquina y, si es la
    // seleccionada, refresca el dot del selector y el badge del header.
    function setMachineStatus(id, status) {
        var opt = document.querySelector('#machineSelect option[value="' + id + '"]');
        if (opt) opt.dataset.status = status;
        if (String(_machineId) === String(id)) updateDot(status);
    }

    // ── Public API ────────────────────────────────────────────────
    window.MS = {
        getMachineId: function () { return _machineId; },
        machineQuery: function (sep) { return _machineId ? sep + 'machine_id=' + _machineId : ''; },
        reload: loadMachines,
        updateDot: updateDot,
        setMachineStatus: setMachineStatus,
    };
})();
