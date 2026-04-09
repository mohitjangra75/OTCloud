from functools import wraps

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

User = get_user_model()


def _role_required(*roles):
    """Factory that creates a decorator restricting access to specific roles."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('accounts:login')
            if request.user.role not in roles:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def admin_required(view_func):
    """Restrict view to admin users only."""
    return _role_required(User.Role.ADMIN)(view_func)


def staff_required(view_func):
    """Restrict view to staff (therapists) and admin users."""
    return _role_required(User.Role.ADMIN, User.Role.STAFF)(view_func)


def client_required(view_func):
    """Restrict view to client users only."""
    return _role_required(User.Role.CLIENT)(view_func)
