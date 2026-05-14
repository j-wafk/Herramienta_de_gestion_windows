// Intercepta fetch globalmente para incluir el token CSRF en todas las
// peticiones que modifican estado (POST, PUT, DELETE, PATCH).
(function () {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (!meta) return;
    const token = meta.content;
    const _fetch = window.fetch;
    window.fetch = function (url, options) {
        options = options || {};
        const method = (options.method || 'GET').toUpperCase();
        if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
            options.headers = Object.assign({}, options.headers, {
                'X-CSRFToken': token
            });
        }
        return _fetch.call(this, url, options);
    };
})();
