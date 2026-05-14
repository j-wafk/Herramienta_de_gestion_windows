// sidebar_info.js — loads system info and populates the sidebar machine panel.
// Include after machine_selector.js on any page that needs the sidebar populated.
(function () {
    function setText(id, val) {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    }

    function mq() {
        return window.MS ? window.MS.machineQuery('?') : '';
    }

    async function loadSidebarInfo() {
        try {
            const r = await fetch('/api/rendimiento/system_info' + mq());
            if (!r.ok) return;
            const d = await r.json();
            if (!d) return;
            setText('sidebarHostname', d.hostname || 'Local');
            const os = d.os || '';
            setText('sidebarOS', os.length > 28 ? os.substring(0, 28) + '…' : os);
            setText('sidebarVersion', d.ip ? 'IP: ' + d.ip : '');
        } catch (_) {}
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', loadSidebarInfo);
    } else {
        loadSidebarInfo();
    }

    window.addEventListener('machineChanged', loadSidebarInfo);
})();
