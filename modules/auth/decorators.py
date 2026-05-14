from functools import wraps
from flask import jsonify, request, redirect, url_for
from flask_login import current_user


def require_role(*roles):
    """
    Decorador de roles. Uso:
        @require_role('superadmin', 'admin')
        def mi_vista(): ...

    - Rutas API (/api/ o /auth/api/): devuelve JSON 401/403.
    - Resto: redirige a /auth/login.
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                if request.path.startswith('/api/') or request.path.startswith('/auth/api/'):
                    return jsonify({'error': 'No autenticado'}), 401
                return redirect(url_for('auth.login', next=request.path))
            if current_user.role not in roles:
                if request.path.startswith('/api/') or request.path.startswith('/auth/api/'):
                    return jsonify({'error': 'Permiso denegado'}), 403
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated
    return decorator
