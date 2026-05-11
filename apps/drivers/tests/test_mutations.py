import pytest
from graphene.test import Client

from apps.agencies.models import Agency
from apps.accounts.factories import AgencyUserFactory
from apps.accounts.models import Role, Permission, RolePermission, UserRole
from apps.drivers.models import Driver
from apps.drivers.factories import DriverFactory
from apps.common.context import set_current_agency, clear_current_agency
from config.schema import schema


PERMS = [
    "drivers.read", "drivers.create", "drivers.update",
    "drivers.suspend", "drivers.offboard", "drivers.note",
]


@pytest.fixture
def ctx(db):
    agency = Agency.objects.create(name="A", slug="a")
    set_current_agency(agency)
    user = AgencyUserFactory(agency=agency, email="op@a.test", password="x", is_active=True)
    role = Role.objects.create(agency=agency, name="Manager")
    for code in PERMS:
        p, _ = Permission.objects.get_or_create(code=code)
        RolePermission.objects.create(role=role, permission=p)
    UserRole.objects.create(user=user, role=role)
    class Req: pass
    req = Req()
    req.user = user
    req.current_agency = agency
    yield agency, user, req
    clear_current_agency()


def _run(query, ctx_req, variables=None):
    return Client(schema).execute(query, context=ctx_req, variables=variables)


def test_create_driver_happy(ctx):
    _, _, req = ctx
    q = """
    mutation { createDriver(input: {firstName: "A", lastName: "B", email: "ab@a.test"}) {
      __typename ... on Success { message } ... on ValidationError { fieldErrors { field message } }
    } }
    """
    r = _run(q, req)
    assert r["data"]["createDriver"]["__typename"] == "Success"
    assert Driver.objects.filter(email="ab@a.test").exists()


def test_create_driver_duplicate_email(ctx):
    agency, _, req = ctx
    DriverFactory(agency=agency, email="dup@a.test")
    q = """
    mutation { createDriver(input: {firstName: "A", lastName: "B", email: "dup@a.test"}) {
      __typename ... on ValidationError { fieldErrors { field message } }
    } }
    """
    r = _run(q, req)
    assert r["data"]["createDriver"]["__typename"] == "ValidationError"


def test_suspend_driver_happy(ctx):
    agency, _, req = ctx
    d = DriverFactory(agency=agency, status=Driver.Status.ACTIVE)
    q = f"""
    mutation {{ suspendDriver(id: "{d.id}", reason: "no-show") {{
      __typename ... on Success {{ message }} ... on ValidationError {{ fieldErrors {{ field message }} }}
    }} }}
    """
    r = _run(q, req)
    assert r["data"]["suspendDriver"]["__typename"] == "Success"
    d.refresh_from_db()
    assert d.status == Driver.Status.SUSPENDED


def test_suspend_already_suspended(ctx):
    agency, _, req = ctx
    d = DriverFactory(agency=agency, status=Driver.Status.SUSPENDED)
    q = f"""mutation {{ suspendDriver(id: "{d.id}", reason: "x") {{ __typename }} }}"""
    r = _run(q, req)
    assert r["data"]["suspendDriver"]["__typename"] == "ValidationError"


def test_offboard_happy(ctx):
    agency, _, req = ctx
    d = DriverFactory(agency=agency, status=Driver.Status.ACTIVE)
    q = f"""mutation {{ offboardDriver(id: "{d.id}", reason: "left") {{ __typename }} }}"""
    r = _run(q, req)
    assert r["data"]["offboardDriver"]["__typename"] == "Success"
    d.refresh_from_db()
    assert d.status == Driver.Status.OFFBOARDED


def test_offboard_already_offboarded(ctx):
    agency, _, req = ctx
    d = DriverFactory(agency=agency, status=Driver.Status.OFFBOARDED)
    q = f"""mutation {{ offboardDriver(id: "{d.id}", reason: "x") {{ __typename }} }}"""
    r = _run(q, req)
    assert r["data"]["offboardDriver"]["__typename"] == "ValidationError"


def test_add_note_happy(ctx):
    agency, _, req = ctx
    d = DriverFactory(agency=agency)
    q = f"""mutation {{ addDriverNote(driverId: "{d.id}", body: "hello") {{ __typename }} }}"""
    r = _run(q, req)
    assert r["data"]["addDriverNote"]["__typename"] == "Success"
    assert d.notes.count() == 1


def test_no_permission_returns_permission_denied(db):
    agency = Agency.objects.create(name="A", slug="a")
    set_current_agency(agency)
    user = AgencyUserFactory(agency=agency, email="poor@a.test", password="x")
    class Req: pass
    req = Req(); req.user = user; req.current_agency = agency
    d = DriverFactory(agency=agency)
    q = f"""mutation {{ addDriverNote(driverId: "{d.id}", body: "x") {{ __typename }} }}"""
    r = _run(q, req)
    assert r["data"]["addDriverNote"]["__typename"] == "PermissionDenied"
    clear_current_agency()


def test_cross_agency_leak_via_driver_query(db):
    a = Agency.objects.create(name="A", slug="a")
    b = Agency.objects.create(name="B", slug="b")
    set_current_agency(b)
    user_b = AgencyUserFactory(agency=b, email="u@b.test", password="x")
    role = Role.objects.create(agency=b, name="Reader")
    p, _ = Permission.objects.get_or_create(code="drivers.read")
    RolePermission.objects.create(role=role, permission=p)
    UserRole.objects.create(user=user_b, role=role)
    a_driver = DriverFactory(agency=a)

    class Req: pass
    req = Req(); req.user = user_b; req.current_agency = b
    q = f"""query {{ driver(id: "{a_driver.id}") {{ id }} }}"""
    r = _run(q, req)
    assert r["data"]["driver"] is None
    clear_current_agency()
