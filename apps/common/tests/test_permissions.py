import pytest
from unittest.mock import MagicMock

from apps.agencies.models import Agency
from apps.accounts.models import AgencyUser, Role, Permission, RolePermission, UserRole
from apps.common.context import set_current_agency, clear_current_agency
from apps.common.permissions import permission_required, has_permission


@pytest.fixture
def user_with_perm(db):
    a = Agency.objects.create(name="A", slug="a")
    set_current_agency(a)
    u = AgencyUser(email="u@a.test", agency=a)
    u.set_password("x")
    u.save()
    perm = Permission.objects.create(code="drivers.read")
    role = Role.objects.create(agency=a, name="Reader")
    RolePermission.objects.create(role=role, permission=perm)
    UserRole.objects.create(user=u, role=role)
    yield u
    clear_current_agency()


def test_has_permission_true(user_with_perm):
    assert has_permission(user_with_perm, "drivers.read") is True


def test_has_permission_false(user_with_perm):
    assert has_permission(user_with_perm, "drivers.suspend") is False


def test_decorator_returns_permission_denied_for_mutation(user_with_perm):
    info = MagicMock()
    info.context.user = user_with_perm

    @permission_required("drivers.suspend")
    def mutate(root, info):
        return "should not reach"

    result = mutate(None, info)
    from apps.common.graphql_types import PermissionDenied
    assert isinstance(result, PermissionDenied)


def test_decorator_allows_when_permission_granted(user_with_perm):
    info = MagicMock()
    info.context.user = user_with_perm

    @permission_required("drivers.read")
    def mutate(root, info):
        return "ok"

    assert mutate(None, info) == "ok"
