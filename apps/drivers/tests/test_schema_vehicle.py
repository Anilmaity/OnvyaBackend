import pytest
from graphene.test import Client
from apps.agencies.models import Agency
from apps.common.context import set_current_agency, clear_current_agency
from apps.accounts.factories import AgencyUserFactory
from apps.drivers.factories import DriverFactory
from apps.vehicles.models import Vehicle
from apps.vehicles.services import VehicleService
from config.schema import schema


@pytest.fixture
def ctx(db):
    a = Agency.objects.create(name="A", slug="a")
    set_current_agency(a)
    user = AgencyUserFactory(agency=a, email="d@a.test", password="x")
    driver = DriverFactory(agency=a, user=user, ni_number="QQ123456C")
    VehicleService().save(Vehicle(driver=driver, registration="LV71 ABC", make="Tesla", model="Model 3", year=2021, colour="Black"))
    class Req: pass
    req = Req(); req.user = user; req.current_agency = a
    yield req
    clear_current_agency()


def test_me_exposes_vehicle_and_ni(ctx):
    q = "query { me { driverProfile { niNumber dbsConsent vehicle { registration make } } } }"
    r = Client(schema).execute(q, context=ctx)
    dp = r["data"]["me"]["driverProfile"]
    assert dp["niNumber"] == "QQ123456C"
    assert dp["vehicle"]["registration"] == "LV71 ABC"
