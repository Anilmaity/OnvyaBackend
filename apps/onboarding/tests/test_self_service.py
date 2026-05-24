import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from graphene.test import Client
from apps.agencies.models import Agency
from apps.common.context import set_current_agency, clear_current_agency
from apps.accounts.factories import AgencyUserFactory
from apps.drivers.factories import DriverFactory
from apps.onboarding.models import Application
from config.schema import schema


@pytest.fixture
def driver_ctx(db):
    a = Agency.objects.create(name="A", slug="a")
    set_current_agency(a)
    user = AgencyUserFactory(agency=a, email="d@a.test", password="x")
    driver = DriverFactory(agency=a, user=user)
    class Req: pass
    req = Req(); req.user = user; req.current_agency = a
    yield a, user, driver, req
    clear_current_agency()


def _run(q, req, variables=None):
    return Client(schema).execute(q, context=req, variables=variables)


def test_start_my_application_creates_for_self(driver_ctx):
    a, user, driver, req = driver_ctx
    r = _run("mutation { startMyApplication { __typename ... on Success { message } } }", req)
    assert r["data"]["startMyApplication"]["__typename"] == "Success"
    assert Application.objects.filter(driver=driver).exists()


def test_start_my_application_no_profile_denied(db):
    a = Agency.objects.create(name="B", slug="b")
    set_current_agency(a)
    user = AgencyUserFactory(agency=a, email="op@b.test", password="x")
    class Req: pass
    req = Req(); req.user = user; req.current_agency = a
    r = _run("mutation { startMyApplication { __typename } }", req)
    clear_current_agency()
    assert r["data"]["startMyApplication"]["__typename"] == "PermissionDenied"


def test_save_my_personal_details(driver_ctx):
    a, user, driver, req = driver_ctx
    _run("mutation { startMyApplication { __typename } }", req)
    q = 'mutation { saveMyPersonalDetails(firstName:"Jane", lastName:"Doe", phone:"7123456789") { __typename ... on Success { message } } }'
    r = _run(q, req)
    assert r["data"]["saveMyPersonalDetails"]["__typename"] == "Success"
    driver.refresh_from_db()
    assert driver.first_name == "Jane" and driver.phone == "7123456789"


def test_save_my_vehicle_upsert(driver_ctx):
    a, user, driver, req = driver_ctx
    _run("mutation { startMyApplication { __typename } }", req)
    q = 'mutation { saveMyVehicle(registration:"LV71 ABC", make:"Tesla", model:"Model 3", year:2021, colour:"Black") { __typename } }'
    assert _run(q, req)["data"]["saveMyVehicle"]["__typename"] == "Success"
    driver.refresh_from_db()
    assert driver.vehicle.make == "Tesla"


def test_save_my_background_check(driver_ctx):
    a, user, driver, req = driver_ctx
    _run("mutation { startMyApplication { __typename } }", req)
    q = 'mutation { saveMyBackgroundCheck(niNumber:"QQ123456C", dbsConsent:true) { __typename } }'
    assert _run(q, req)["data"]["saveMyBackgroundCheck"]["__typename"] == "Success"
    driver.refresh_from_db()
    assert driver.ni_number == "QQ123456C" and driver.dbs_consent is True


def test_background_check_requires_consent(driver_ctx):
    a, user, driver, req = driver_ctx
    _run("mutation { startMyApplication { __typename } }", req)
    q = 'mutation { saveMyBackgroundCheck(niNumber:"QQ123456C", dbsConsent:false) { __typename } }'
    assert _run(q, req)["data"]["saveMyBackgroundCheck"]["__typename"] == "ValidationError"


def test_driver_uploads_to_own_application(driver_ctx):
    a, user, driver, req = driver_ctx
    from apps.onboarding.services import ApplicationService
    app = ApplicationService().start(driver)
    f = SimpleUploadedFile("l.pdf", b"x", content_type="application/pdf")
    r = Client(schema).execute(
        'mutation($f: Upload!) { uploadApplicationDocument(applicationId: "%s", kind: "LICENCE", file: $f) { __typename } }' % app.id,
        context=req, variables={"f": f},
    )
    assert r["data"]["uploadApplicationDocument"]["__typename"] == "Success"
