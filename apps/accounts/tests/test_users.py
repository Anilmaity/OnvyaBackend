import pytest
from graphene.test import Client

from apps.agencies.models import Agency
from apps.accounts.models import AgencyUser, Role, Permission, RolePermission, UserRole
from apps.accounts.factories import AgencyUserFactory
from apps.common.context import set_current_agency, clear_current_agency
from config.schema import schema


ACCOUNT_PERMS = ["accounts.read", "accounts.manage"]


@pytest.fixture
def ctx(db):
    agency = Agency.objects.create(name="A", slug="a")
    set_current_agency(agency)
    actor = AgencyUserFactory(agency=agency, email="actor@a.test", password="x")
    role = Role.objects.create(agency=agency, name="Admin")
    for code in ACCOUNT_PERMS:
        p, _ = Permission.objects.get_or_create(code=code)
        RolePermission.objects.create(role=role, permission=p)
    UserRole.objects.create(user=actor, role=role)
    target_role = Role.objects.create(agency=agency, name="Recruiter")
    class Req: pass
    req = Req(); req.user = actor; req.current_agency = agency
    yield agency, actor, target_role, req
    clear_current_agency()


def _run(q, req, variables=None):
    return Client(schema).execute(q, context=req, variables=variables)


def test_me_returns_permissions(ctx):
    _, _, _, req = ctx
    q = """query { me { email permissions roles { name } } }"""
    r = _run(q, req)
    perms = r["data"]["me"]["permissions"]
    assert "accounts.read" in perms and "accounts.manage" in perms
    role_names = [x["name"] for x in r["data"]["me"]["roles"]]
    assert "Admin" in role_names


def test_agency_users_scoped(ctx):
    agency, _, _, req = ctx
    AgencyUserFactory(agency=agency, email="u1@a.test", password="x")
    other = Agency.objects.create(name="B", slug="b")
    AgencyUserFactory(agency=other, email="u@b.test", password="x")
    q = """query { agencyUsers { email } }"""
    r = _run(q, req)
    emails = {u["email"] for u in r["data"]["agencyUsers"]}
    assert "u1@a.test" in emails
    assert "u@b.test" not in emails


def test_create_agency_user_happy(ctx):
    _, _, target_role, req = ctx
    q = f"""
    mutation {{ createAgencyUser(input: {{
        email: "new@a.test", firstName: "New", lastName: "User",
        password: "demo1234", roleIds: ["{target_role.id}"]
    }}) {{ __typename ... on Success {{ id }} }} }}
    """
    r = _run(q, req)
    assert r["data"]["createAgencyUser"]["__typename"] == "Success"
    assert AgencyUser.objects.filter(email="new@a.test").exists()


def test_create_agency_user_duplicate(ctx):
    agency, _, target_role, req = ctx
    AgencyUserFactory(agency=agency, email="dup@a.test", password="x")
    q = f"""
    mutation {{ createAgencyUser(input: {{
        email: "dup@a.test", firstName: "X", lastName: "Y",
        password: "demo1234", roleIds: ["{target_role.id}"]
    }}) {{ __typename }} }}
    """
    r = _run(q, req)
    assert r["data"]["createAgencyUser"]["__typename"] == "ValidationError"


def test_create_agency_user_no_permission(db):
    agency = Agency.objects.create(name="A", slug="a")
    set_current_agency(agency)
    poor = AgencyUserFactory(agency=agency, email="poor@a.test", password="x")
    target_role = Role.objects.create(agency=agency, name="Reader")
    class Req: pass
    req = Req(); req.user = poor; req.current_agency = agency
    q = f"""
    mutation {{ createAgencyUser(input: {{
        email: "x@a.test", firstName: "X", lastName: "Y",
        password: "demo1234", roleIds: ["{target_role.id}"]
    }}) {{ __typename }} }}
    """
    r = _run(q, req)
    assert r["data"]["createAgencyUser"]["__typename"] == "PermissionDenied"
    clear_current_agency()


def test_assign_and_revoke_role(ctx):
    agency, _, target_role, req = ctx
    user = AgencyUserFactory(agency=agency, email="u2@a.test", password="x")
    assign = f"""
    mutation {{ assignRole(userId: "{user.id}", roleId: "{target_role.id}") {{ __typename }} }}
    """
    assert _run(assign, req)["data"]["assignRole"]["__typename"] == "Success"
    assert UserRole.objects.filter(user=user, role=target_role).exists()
    revoke = f"""
    mutation {{ revokeRole(userId: "{user.id}", roleId: "{target_role.id}") {{ __typename }} }}
    """
    assert _run(revoke, req)["data"]["revokeRole"]["__typename"] == "Success"
    assert not UserRole.objects.filter(user=user, role=target_role).exists()


def test_deactivate_user_happy(ctx):
    agency, _, _, req = ctx
    user = AgencyUserFactory(agency=agency, email="dead@a.test", password="x")
    q = f"""mutation {{ deactivateAgencyUser(userId: "{user.id}") {{ __typename }} }}"""
    assert _run(q, req)["data"]["deactivateAgencyUser"]["__typename"] == "Success"
    user.refresh_from_db()
    assert user.is_active is False


def test_cannot_self_deactivate(ctx):
    _, actor, _, req = ctx
    q = f"""mutation {{ deactivateAgencyUser(userId: "{actor.id}") {{ __typename }} }}"""
    assert _run(q, req)["data"]["deactivateAgencyUser"]["__typename"] == "ValidationError"


def test_me_driver_profile_returns_driver(ctx):
    agency, actor, _, _ = ctx
    from apps.drivers.models import Driver
    Driver.objects.create(
        agency=agency, user=actor,
        first_name="Drive", last_name="R", email="actor@a.test",
        status=Driver.Status.ACTIVE,
    )
    actor.refresh_from_db()
    q = """query { me { driverProfile { firstName lastName status } } }"""
    class Req: pass
    req = Req(); req.user = actor; req.current_agency = agency
    r = _run(q, req)
    assert r["data"]["me"]["driverProfile"]["firstName"] == "Drive"
    assert r["data"]["me"]["driverProfile"]["status"] == "ACTIVE"


def test_me_driver_profile_returns_null_when_absent(ctx):
    _, actor, _, _ = ctx
    q = """query { me { driverProfile { firstName } } }"""
    class Req: pass
    req = Req(); req.user = actor; req.current_agency = None
    r = _run(q, req)
    assert r["data"]["me"]["driverProfile"] is None
