from functools import wraps

from apps.common.graphql_types import PermissionDenied


def has_permission(user, code):
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    cache_attr = "_perm_codes_cache"
    if not hasattr(user, cache_attr):
        codes = set(
            user.user_roles.values_list("role__role_permissions__permission__code", flat=True)
        )
        codes.discard(None)
        setattr(user, cache_attr, codes)
    return code in getattr(user, cache_attr)


def permission_required(code):
    def decorator(resolver):
        @wraps(resolver)
        def wrapper(root, info, *args, **kwargs):
            user = getattr(info.context, "user", None)
            if not has_permission(user, code):
                return PermissionDenied(code="permission_denied", message=f"Missing permission: {code}")
            return resolver(root, info, *args, **kwargs)
        return wrapper
    return decorator
