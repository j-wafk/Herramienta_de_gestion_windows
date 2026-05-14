/* profile_modal.js — panel de perfil de usuario */
(function () {
    'use strict';

    const AVATAR_COLORS = [
        '#0A67DC', '#2EA043', '#7C3AED', '#dc2626',
        '#f59e0b', '#0d9488', '#ec4899', '#64748b',
    ];

    // Eventos de notificación por email (deben coincidir con backend
    // NotificationPreference en database/models.py).
    const NOTIF_EVENTS = [
        { key: 'machine_offline',  id: 'pmNotifMachineOffline' },
        { key: 'service_down',     id: 'pmNotifServiceDown' },
        { key: 'backup_failed',    id: 'pmNotifBackupFailed' },
        { key: 'backup_completed', id: 'pmNotifBackupCompleted' },
        { key: 'daily_summary',    id: 'pmNotifDailySummary' },
    ];

    let _profileData  = null;
    let _currentTab   = 'info';
    let _pendingColor = null;
    let _notifPrefs   = null;

    // ── Crear DOM del modal ────────────────────────────────────────────────────

    function _buildModal() {
        if (document.getElementById('profileModal')) return;

        const swatches = AVATAR_COLORS.map(c =>
            `<span class="pm-color-swatch" data-color="${c}" style="background:${c}"
                  onclick="window._pm.pickColor('${c}')"></span>`
        ).join('');

        const T = window.i18n ? window.i18n.t.bind(window.i18n) : (k => k);
        const html = `
<div id="profileModal" class="pm-overlay" style="display:none">
  <div class="pm-box" role="dialog" aria-modal="true" aria-label="${T('pm.tabInfo')}">
    <!-- Header -->
    <div class="pm-header">
      <div class="pm-header-user">
        <div class="pm-header-avatar" id="pmHeaderAvatar">?</div>
        <div>
          <div class="pm-header-name" id="pmHeaderName">—</div>
          <span class="pm-header-role" id="pmHeaderRole">—</span>
        </div>
      </div>
      <button class="pm-close" onclick="window._pm.close()" data-i18n-attr="title" data-i18n="pm.close" title="${T('pm.close')}">&#x2715;</button>
    </div>
    <!-- Tabs -->
    <div class="pm-tabs">
      <button class="pm-tab-btn active" data-tab="info"     onclick="window._pm.tab('info')"     data-i18n="pm.tabInfo">${T('pm.tabInfo')}</button>
      <button class="pm-tab-btn"        data-tab="security" onclick="window._pm.tab('security')" data-i18n="pm.tabSecurity">${T('pm.tabSecurity')}</button>
      <button class="pm-tab-btn"        data-tab="prefs"    onclick="window._pm.tab('prefs')"    data-i18n="pm.tabPrefs">${T('pm.tabPrefs')}</button>
    </div>
    <!-- Mensaje -->
    <div class="pm-message" id="pmMessage" role="alert"></div>
    <!-- Panel: Información -->
    <div class="pm-tab-panel active" data-tab="info">
      <div class="pm-section">
        <label class="pm-label" data-i18n="pm.avatar">${T('pm.avatar')}</label>
        <div class="pm-avatar-picker">
          <div class="pm-avatar-preview" id="pmAvatarPreview">?</div>
          <div class="pm-color-swatches">${swatches}</div>
        </div>
      </div>
      <div class="pm-section">
        <label class="pm-label" for="pmFullName" data-i18n="pm.fullName">${T('pm.fullName')}</label>
        <input type="text" id="pmFullName" class="pm-input" placeholder="${T('pm.fullNamePh')}" maxlength="120"
               data-i18n-attr="placeholder" data-i18n="pm.fullNamePh"
               oninput="window._pm.syncAvatar()">
      </div>
      <div class="pm-section">
        <label class="pm-label" for="pmEmail" data-i18n="pm.email">${T('pm.email')}</label>
        <input type="email" id="pmEmail" class="pm-input" placeholder="${T('pm.emailPh')}"
               data-i18n-attr="placeholder" data-i18n="pm.emailPh">
      </div>
      <div class="pm-section pm-readonly-grid">
        <div><label class="pm-label" data-i18n="pm.username">${T('pm.username')}</label>     <div class="pm-readonly-val" id="pmUsername">—</div></div>
        <div><label class="pm-label" data-i18n="pm.role">${T('pm.role')}</label>              <div class="pm-readonly-val" id="pmRole">—</div></div>
        <div><label class="pm-label" data-i18n="pm.lastLogin">${T('pm.lastLogin')}</label>   <div class="pm-readonly-val" id="pmLastLogin">—</div></div>
        <div><label class="pm-label" data-i18n="pm.memberSince">${T('pm.memberSince')}</label><div class="pm-readonly-val" id="pmCreatedAt">—</div></div>
      </div>
      <div class="pm-footer">
        <button class="pm-btn-primary" id="pmSaveInfoBtn" onclick="window._pm.saveInfo()" data-i18n="pm.saveChanges">${T('pm.saveChanges')}</button>
      </div>
    </div>
    <!-- Panel: Seguridad -->
    <div class="pm-tab-panel" data-tab="security">
      <div class="pm-section">
        <label class="pm-label" for="pmCurrentPass" data-i18n="pm.currentPass">${T('pm.currentPass')}</label>
        <input type="password" id="pmCurrentPass" class="pm-input" placeholder="${T('pm.currentPassPh')}"
               data-i18n-attr="placeholder" data-i18n="pm.currentPassPh" autocomplete="current-password">
      </div>
      <div class="pm-section">
        <label class="pm-label" for="pmNewPass" data-i18n="pm.newPass">${T('pm.newPass')}</label>
        <input type="password" id="pmNewPass" class="pm-input" placeholder="${T('pm.newPassPh')}"
               data-i18n-attr="placeholder" data-i18n="pm.newPassPh"
               autocomplete="new-password" oninput="window._pm.strengthUpdate(this.value)">
        <div class="pm-strength-wrap">
          <div class="pm-strength-track"><div class="pm-strength-bar" id="pmStrengthBar"></div></div>
          <span class="pm-strength-label" id="pmStrengthLabel"></span>
        </div>
      </div>
      <div class="pm-section">
        <label class="pm-label" for="pmConfirmPass" data-i18n="pm.confirmPass">${T('pm.confirmPass')}</label>
        <input type="password" id="pmConfirmPass" class="pm-input" placeholder="${T('pm.confirmPassPh')}"
               data-i18n-attr="placeholder" data-i18n="pm.confirmPassPh" autocomplete="new-password">
      </div>
      <div class="pm-footer">
        <button class="pm-btn-primary" id="pmChangePassBtn" onclick="window._pm.changePassword()" data-i18n="pm.changePass">${T('pm.changePass')}</button>
      </div>
    </div>
    <!-- Panel: Preferencias -->
    <div class="pm-tab-panel" data-tab="prefs">
      <div class="pm-section">
        <label class="pm-label" for="pmLanguage" data-i18n="pm.language">${T('pm.language')}</label>
        <select id="pmLanguage" class="pm-input">
          <option value="es">Español</option>
          <option value="en">English</option>
        </select>
      </div>
      <div class="pm-section">
        <label class="pm-label" for="pmTheme" data-i18n="pm.theme">${T('pm.theme')}</label>
        <select id="pmTheme" class="pm-input">
          <option value="light" data-i18n="pm.themeLight">${T('pm.themeLight')}</option>
          <option value="dark"  data-i18n="pm.themeDark">${T('pm.themeDark')}</option>
        </select>
      </div>
      <div class="pm-section pm-toggle-row">
        <div>
          <div class="pm-label" data-i18n="pm.emailNotif">${T('pm.emailNotif')}</div>
          <div class="pm-sublabel" data-i18n="pm.emailNotifSub">${T('pm.emailNotifSub')}</div>
        </div>
        <label class="pm-toggle">
          <input type="checkbox" id="pmEmailNotif">
          <span class="pm-toggle-track"></span>
        </label>
      </div>
      <div class="pm-section pm-notif-events" id="pmNotifEvents">
        <div class="pm-label" data-i18n="pm.notifEvents">${T('pm.notifEvents')}</div>
        <div class="pm-sublabel" data-i18n="pm.notifEventsSub">${T('pm.notifEventsSub')}</div>
        <div class="pm-toggle-row">
          <div>
            <div class="pm-label" data-i18n="pm.notifMachineOffline">${T('pm.notifMachineOffline')}</div>
            <div class="pm-sublabel" data-i18n="pm.notifMachineOfflineSub">${T('pm.notifMachineOfflineSub')}</div>
          </div>
          <label class="pm-toggle"><input type="checkbox" id="pmNotifMachineOffline"><span class="pm-toggle-track"></span></label>
        </div>
        <div class="pm-toggle-row">
          <div>
            <div class="pm-label" data-i18n="pm.notifServiceDown">${T('pm.notifServiceDown')}</div>
            <div class="pm-sublabel" data-i18n="pm.notifServiceDownSub">${T('pm.notifServiceDownSub')}</div>
          </div>
          <label class="pm-toggle"><input type="checkbox" id="pmNotifServiceDown"><span class="pm-toggle-track"></span></label>
        </div>
        <div class="pm-toggle-row">
          <div>
            <div class="pm-label" data-i18n="pm.notifBackupFailed">${T('pm.notifBackupFailed')}</div>
            <div class="pm-sublabel" data-i18n="pm.notifBackupFailedSub">${T('pm.notifBackupFailedSub')}</div>
          </div>
          <label class="pm-toggle"><input type="checkbox" id="pmNotifBackupFailed"><span class="pm-toggle-track"></span></label>
        </div>
        <div class="pm-toggle-row">
          <div>
            <div class="pm-label" data-i18n="pm.notifBackupCompleted">${T('pm.notifBackupCompleted')}</div>
            <div class="pm-sublabel" data-i18n="pm.notifBackupCompletedSub">${T('pm.notifBackupCompletedSub')}</div>
          </div>
          <label class="pm-toggle"><input type="checkbox" id="pmNotifBackupCompleted"><span class="pm-toggle-track"></span></label>
        </div>
        <div class="pm-toggle-row">
          <div>
            <div class="pm-label" data-i18n="pm.notifDailySummary">${T('pm.notifDailySummary')}</div>
            <div class="pm-sublabel" data-i18n="pm.notifDailySummarySub">${T('pm.notifDailySummarySub')}</div>
          </div>
          <label class="pm-toggle"><input type="checkbox" id="pmNotifDailySummary"><span class="pm-toggle-track"></span></label>
        </div>
      </div>
      <div class="pm-footer">
        <button class="pm-btn-primary" id="pmSavePrefBtn" onclick="window._pm.savePreferences()" data-i18n="pm.savePrefs">${T('pm.savePrefs')}</button>
      </div>
    </div>
  </div>
</div>`;

        document.body.insertAdjacentHTML('beforeend', html);

        // Cerrar al clicar overlay
        document.getElementById('profileModal').addEventListener('click', function (e) {
            if (e.target === this) window._pm.close();
        });
    }

    // ── Helpers ────────────────────────────────────────────────────────────────

    function _getInitials(name) {
        if (!name) return '?';
        const parts = name.trim().split(/\s+/).filter(Boolean);
        if (parts.length === 1) return parts[0][0].toUpperCase();
        return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    }

    function _fmtDate(iso) {
        if (!iso) return window.i18n ? window.i18n.t('pm.never') : 'Nunca';
        try {
            const locale = (document.documentElement.lang === 'en') ? 'en-US' : 'es-ES';
            const d = new Date(iso);
            return d.toLocaleDateString(locale, { day: '2-digit', month: '2-digit', year: 'numeric' })
                + ' ' + d.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
        } catch { return iso; }
    }

    function _csrf() {
        return document.querySelector('meta[name="csrf-token"]')?.content || '';
    }

    function _setText(id, val) {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    }

    function _showMsg(msg, type) {
        const el = document.getElementById('pmMessage');
        if (!el) return;
        el.textContent = msg;
        el.className = 'pm-message' + (type ? ' pm-message--' + type : '');
        if (type === 'ok') setTimeout(() => { if (el.textContent === msg) { el.textContent = ''; el.className = 'pm-message'; } }, 3500);
    }

    function _clearMsg() {
        const el = document.getElementById('pmMessage');
        if (el) { el.textContent = ''; el.className = 'pm-message'; }
    }

    function _populate(data) {
        const initials = _getInitials(data.full_name || data.username);
        const color    = data.avatar_color || '#0A67DC';

        // Header del modal
        const ha = document.getElementById('pmHeaderAvatar');
        if (ha) { ha.textContent = initials; ha.style.background = color; }
        _setText('pmHeaderName', data.full_name || data.username);
        _setText('pmHeaderRole', data.role);

        // Pestaña Info
        const ap = document.getElementById('pmAvatarPreview');
        if (ap) { ap.textContent = initials; ap.style.background = color; }
        document.getElementById('pmFullName').value = data.full_name || '';
        document.getElementById('pmEmail').value    = data.email    || '';
        _setText('pmUsername',  data.username);
        _setText('pmRole',      data.role);
        _setText('pmLastLogin', _fmtDate(data.last_login));
        _setText('pmCreatedAt', _fmtDate(data.created_at));

        // Seleccionar swatch del color activo
        _pendingColor = color;
        document.querySelectorAll('.pm-color-swatch').forEach(s => {
            s.classList.toggle('active', s.dataset.color === color);
        });

        // Pestaña Preferencias
        document.getElementById('pmLanguage').value     = data.language || 'es';
        document.getElementById('pmTheme').value        = data.theme    || 'light';
        const emailNotifEl = document.getElementById('pmEmailNotif');
        emailNotifEl.checked = !!data.email_notifications;
        _updateNotifEventsEnabled();
    }

    function _populateNotifPrefs(prefs) {
        if (!prefs) return;
        NOTIF_EVENTS.forEach(({ key, id }) => {
            const el = document.getElementById(id);
            if (el) el.checked = !!prefs[key];
        });
    }

    // Si el toggle maestro "Recibir alertas del sistema por correo" está OFF,
    // los toggles por evento quedan visualmente atenuados/deshabilitados — el
    // backend respeta siempre los toggles individuales, pero esto deja claro
    // que no se enviará nada si el maestro está apagado.
    function _updateNotifEventsEnabled() {
        const master  = document.getElementById('pmEmailNotif');
        const wrapper = document.getElementById('pmNotifEvents');
        if (!master || !wrapper) return;
        const on = master.checked;
        wrapper.classList.toggle('pm-disabled', !on);
        NOTIF_EVENTS.forEach(({ id }) => {
            const el = document.getElementById(id);
            if (el) el.disabled = !on;
        });
    }

    function _updateHeader(data) {
        const initials = _getInitials(data.full_name || data.username);
        const color    = data.avatar_color || '#0A67DC';
        const hdrAv    = document.getElementById('hdrAvatar');
        if (hdrAv)  { hdrAv.textContent = initials; hdrAv.style.background = color; }
        const hdrNm  = document.getElementById('hdrUsername');
        if (hdrNm)  hdrNm.textContent = data.full_name || data.username;
    }

    // ── API pública (window._pm) ───────────────────────────────────────────────

    window._pm = {

        open: function () {
            _buildModal();
            if (window.i18n) window.i18n.apply();
            document.getElementById('profileModal').style.display = 'flex';
            _currentTab = 'info';
            _clearMsg();
            // Resetear pestañas al abrir
            document.querySelectorAll('.pm-tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === 'info'));
            document.querySelectorAll('.pm-tab-panel').forEach(p => p.classList.toggle('active', p.dataset.tab === 'info'));
            // El toggle maestro atenúa los toggles por evento al apagarse
            const master = document.getElementById('pmEmailNotif');
            if (master && !master.dataset.bound) {
                master.addEventListener('change', _updateNotifEventsEnabled);
                master.dataset.bound = '1';
            }
            this.fetchProfile();
            this.fetchNotifPrefs();
        },

        close: function () {
            const m = document.getElementById('profileModal');
            if (m) m.style.display = 'none';
        },

        tab: function (tab) {
            _currentTab = tab;
            document.querySelectorAll('.pm-tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
            document.querySelectorAll('.pm-tab-panel').forEach(p => p.classList.toggle('active', p.dataset.tab === tab));
            _clearMsg();
        },

        fetchProfile: async function () {
            try {
                const res = await fetch('/auth/api/profile');
                if (!res.ok) return;
                _profileData = await res.json();
                _populate(_profileData);
            } catch {}
        },

        fetchNotifPrefs: async function () {
            try {
                const res = await fetch('/auth/api/profile/notifications');
                if (!res.ok) return;
                _notifPrefs = await res.json();
                _populateNotifPrefs(_notifPrefs);
            } catch {}
        },

        pickColor: function (color) {
            _pendingColor = color;
            document.querySelectorAll('.pm-color-swatch').forEach(s => {
                s.classList.toggle('active', s.dataset.color === color);
            });
            const ap = document.getElementById('pmAvatarPreview');
            if (ap) ap.style.background = color;
            const ha = document.getElementById('pmHeaderAvatar');
            if (ha) ha.style.background = color;
        },

        syncAvatar: function () {
            const name     = document.getElementById('pmFullName')?.value || _profileData?.username || '';
            const initials = _getInitials(name);
            const ap = document.getElementById('pmAvatarPreview');
            if (ap) ap.textContent = initials;
            const ha = document.getElementById('pmHeaderAvatar');
            if (ha) ha.textContent = initials;
        },

        saveInfo: async function () {
            const btn = document.getElementById('pmSaveInfoBtn');
            if (btn) btn.disabled = true;
            try {
                const res = await fetch('/auth/api/profile/update', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _csrf() },
                    body: JSON.stringify({
                        full_name:    document.getElementById('pmFullName')?.value.trim() || '',
                        email:        document.getElementById('pmEmail')?.value.trim()    || '',
                        avatar_color: _pendingColor || _profileData?.avatar_color || '#0A67DC',
                    }),
                });
                const data = await res.json();
                const T = window.i18n ? window.i18n.t.bind(window.i18n) : (k => k);
                if (!res.ok) { _showMsg(data.error || T('msg.saveError'), 'error'); return; }
                _profileData = data;
                _populate(data);
                _updateHeader(data);
                _showMsg(T('msg.saved'), 'ok');
            } catch { const T = window.i18n ? window.i18n.t.bind(window.i18n) : (k => k); _showMsg(T('msg.connError'), 'error'); }
            finally { if (btn) btn.disabled = false; }
        },

        changePassword: async function () {
            const btn = document.getElementById('pmChangePassBtn');
            if (btn) btn.disabled = true;
            try {
                const res = await fetch('/auth/api/profile/password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _csrf() },
                    body: JSON.stringify({
                        current_password: document.getElementById('pmCurrentPass')?.value || '',
                        new_password:     document.getElementById('pmNewPass')?.value     || '',
                        confirm_password: document.getElementById('pmConfirmPass')?.value || '',
                    }),
                });
                const data = await res.json();
                const T = window.i18n ? window.i18n.t.bind(window.i18n) : (k => k);
                if (!res.ok) { _showMsg(data.error || T('msg.passError'), 'error'); return; }
                ['pmCurrentPass', 'pmNewPass', 'pmConfirmPass'].forEach(id => {
                    const el = document.getElementById(id); if (el) el.value = '';
                });
                this.strengthUpdate('');
                _showMsg(T('msg.passChanged'), 'ok');
            } catch { const T = window.i18n ? window.i18n.t.bind(window.i18n) : (k => k); _showMsg(T('msg.connError'), 'error'); }
            finally { if (btn) btn.disabled = false; }
        },

        savePreferences: async function () {
            const btn = document.getElementById('pmSavePrefBtn');
            if (btn) btn.disabled = true;
            const T = window.i18n ? window.i18n.t.bind(window.i18n) : (k => k);

            const notifBody = {};
            NOTIF_EVENTS.forEach(({ key, id }) => {
                const el = document.getElementById(id);
                if (el) notifBody[key] = !!el.checked;
            });

            try {
                const [profRes, notifRes] = await Promise.all([
                    fetch('/auth/api/profile/update', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _csrf() },
                        body: JSON.stringify({
                            language:            document.getElementById('pmLanguage')?.value || 'es',
                            theme:               document.getElementById('pmTheme')?.value    || 'light',
                            email_notifications: document.getElementById('pmEmailNotif')?.checked || false,
                        }),
                    }),
                    fetch('/auth/api/profile/notifications', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _csrf() },
                        body: JSON.stringify(notifBody),
                    }),
                ]);
                const profData  = await profRes.json().catch(() => ({}));
                const notifData = await notifRes.json().catch(() => ({}));
                if (!profRes.ok)  { _showMsg(profData.error  || T('msg.saveError'), 'error'); return; }
                if (!notifRes.ok) { _showMsg(notifData.error || T('msg.saveError'), 'error'); return; }
                _profileData = profData;
                _notifPrefs  = notifData;
                _showMsg(T('msg.prefsSaved'), 'ok');
                if (window.setTheme)    window.setTheme(document.getElementById('pmTheme')?.value    || 'light');
                if (window.setLanguage) window.setLanguage(document.getElementById('pmLanguage')?.value || 'es');
            } catch { _showMsg(T('msg.connError'), 'error'); }
            finally { if (btn) btn.disabled = false; }
        },

        strengthUpdate: function (pw) {
            const bar   = document.getElementById('pmStrengthBar');
            const label = document.getElementById('pmStrengthLabel');
            if (!bar || !label) return;
            if (!pw) { bar.style.width = '0'; bar.style.background = '#e5e7eb'; label.textContent = ''; return; }
            let score = 0;
            if (pw.length >= 12)          score++;
            if (/[A-Z]/.test(pw))         score++;
            if (/[a-z]/.test(pw))         score++;
            if (/\d/.test(pw))            score++;
            if (/[^A-Za-z0-9]/.test(pw)) score++;
            const T = window.i18n ? window.i18n.t.bind(window.i18n) : (k => k);
            const labels = ['', T('pw.veryWeak'), T('pw.weak'), T('pw.fair'), T('pw.strong'), T('pw.veryStrong')];
            const colors = ['', '#dc2626', '#f59e0b', '#eab308', '#2EA043', '#0A67DC'];
            bar.style.width      = (score * 20) + '%';
            bar.style.background = colors[score];
            label.textContent    = labels[score];
            label.style.color    = colors[score];
        },
    };

    // ── Alias global para llamadas desde onclick del HTML del trigger ──────────
    window.openProfileModal = function () { window._pm.open(); };

    // ── Cerrar con Escape ──────────────────────────────────────────────────────
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') window._pm.close();
    });

    // ── Aplicar color del avatar al cargar la página ───────────────────────────
    document.addEventListener('DOMContentLoaded', function () {
        const av = document.getElementById('hdrAvatar');
        if (av && av.dataset.color) av.style.background = av.dataset.color;
    });

})();
