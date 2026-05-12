from functools import wraps

from graphql import GraphQLList, GraphQLNonNull

from apps.common.graphql_types import MutationResult, PermissionDenied


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


def _denied_value(info, code):
    """Return a value compatible with the resolver's return type when permission is denied.

    - List fields (including NonNull lists) -> [] so GraphQL can serialize them.
    - MutationResult union fields -> PermissionDenied object.
    - Other (e.g. plain object) -> None when nullable, else PermissionDenied as last resort.
    """
    return_type = getattr(info, "return_type", None)
    inner = return_type
    if isinstance(inner, GraphQLNonNull):
        inner = inner.of_type
    if isinstance(inner, GraphQLList):
        return []
    return PermissionDenied(code="permission_denied", message=f"Missing permission: {code}")


def permission_required(code):
    def decorator(resolver):
        @wraps(resolver)
        def wrapper(root, info, *args, **kwargs):
            user = getattr(info.context, "user", None)
            if not has_permission(user, code):
                return _denied_value(info, code)
            return resolver(root, info, *args, **kwargs)
        return wrapper
    return decorator
