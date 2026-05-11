import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from graphene.test import Client

from apps.agencies.models import Agency
from apps.accounts.factories import AgencyUserFactory
from apps.accounts.models import Role, Permission, RolePermission, UserRole
from apps.drivers.factories import DriverFactory
from apps.onboarding.models import Application
from apps.onboarding.services import ApplicationService
from apps.common.context import set_current_agency, clear_current_agency
from config.schema import schema


PERMS = [
    "applications.read", "applications.create",
    "applications.update", "applications.approve",
]


@pytest.fixture
def ctx(db):
    agency = Agency.objects.create(name="A", slug="a")
    set_current_agency(agency)
    Role.objects.create(agency=agency, name="Driver", is_system=True)
    user = AgencyUserFactory(agency=agency, email="op@a.test", password="x")
    role = Role.objects.create(agency=agency, name="Recruiter")
    for code in PERMS:
        p, _ = Permission.objects.get_or_create(code=code)
        RolePermission.objects.create(role=role, permission=p)
    UserRole.objects.create(user=user, role=role)
    class Req: pass
    req = Req(); req.user = user; req.current_agency = agency
    yield agency, user, req
    clear_current_agency()


def _run(q, req, variables=None):
    return Client(schema).execute(q, context=req, variables=variables)


def test_start_application_happy(ctx):
    agency, _, req = ctx
    d = DriverFactory(agency=agency)
    q = f"""mutation {{ startApplication(driverId: "{d.id}") {{ __typename ... on Success {{ id }} }} }}"""
    r = _run(q, req)
    assert r["data"]["startApplication"]["__typename"] == "Success"
    assert Application.objects.filter(driver=d).exists()


def test_start_application_duplicate(ctx):
    agency, _, req = ctx
    d = DriverFactory(agency=agency)
    ApplicationService().start(d)
    q = f"""mutation {{ startApplication(driverId: "{d.id}") {{ __typename }} }}"""
    r = _run(q, req)
    assert r["data"]["startApplication"]["__typename"] == "ValidationError"


def test_submit_then_approve_via_graphql(ctx):
    agency, op, req = ctx
    d = DriverFactory(agency=agency)
    app = ApplicationService().start(d)
    f = SimpleUploadedFile("l.pdf", b"x", content_type="application/pdf")
    ApplicationService().upload_document(app, "LICENCE", f)
    q_submit = f"""mutation {{ submitApplicationForReview(applicationId: "{app.id}") {{ __typename }} }}"""
    assert _run(q_submit, req)["data"]["submitApplicationForReview"]["__typename"] == "Success"
    q_app = f"""mutation {{ approveApplication(applicationId: "{app.id}") {{ __typename }} }}"""
    assert _run(q_app, req)["data"]["approveApplication"]["__typename"] == "Success"


def test_approve_wrong_state(ctx):
    agency, _, req = ctx
    d = DriverFactory(agency=agency)
    app = ApplicationService().start(d)
    q = f"""mutation {{ approveApplication(applicationId: "{app.id}") {{ __typename }} }}"""
    assert _run(q, req)["data"]["approveApplication"]["__typename"] == "ValidationError"


def test_reject_application_offboards(ctx):
    agency, op, req = ctx
    d = DriverFactory(agency=agency)
    app = ApplicationService().start(d)
    f = SimpleUploadedFile("l.pdf", b"x", content_type="application/pdf")
    ApplicationService().upload_document(app, "LICENCE", f)
    ApplicationService().submit_for_review(app)
    q = f"""mutation {{ rejectApplication(applicationId: "{app.id}", reason: "missing docs") {{ __typename }} }}"""
    assert _run(q, req)["data"]["rejectApplication"]["__typename"] == "Success"
