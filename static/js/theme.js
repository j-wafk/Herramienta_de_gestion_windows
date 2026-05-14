/* theme.js — Aplica el tema (light/dark) y sincroniza localStorage.
 *
 * El tema se renderiza desde Flask en html[data-theme="..."].
 * Este módulo expone window.setTheme(t) y window.setLanguage(l)
 * para cambios en tiempo real desde el modal de preferencias.
 *
 * Para la página de login (sin sesión) se lee/escribe localStorage
 * antes del DOMContentLoaded para evitar FOUC.
 */
(function () {
    'use strict';

    // Sincroniza localStorage con el valor ya renderizado por Flask.
    // Así la página de login (sin sesión) lo puede leer.
    var _theme = document.documentElement.getAttribute('data-theme') || 'light';
    var _lang  = document.documentElement.lang || 'es';
    localStorage.setItem('userTheme', _theme);
    localStorage.setItem('userLang',  _lang);

    window.setTheme = function (theme) {
        theme = (theme === 'dark') ? 'dark' : 'light';
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('userTheme', theme);
    };

    window.setLanguage = function (lang) {
        lang = (lang === 'en') ? 'en' : 'es';
        document.documentElement.lang = lang;
        localStorage.setItem('userLang', lang);
        if (window.i18n) window.i18n.apply(lang);
    };
})();
