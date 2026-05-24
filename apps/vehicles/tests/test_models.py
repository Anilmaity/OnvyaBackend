import pytest
from apps.agencies.models import Agency
from apps.common.context import set_current_agency, clear_current_agency
from apps.drivers.factories import DriverFactory
from apps.vehicles.models import Vehicle
from apps.vehicles.services import VehicleService


@pytest.fixture
def agency(db):
    a = Agency.objects.create(name="A", slug="a")
    set_current_agency(a)
    yield a
    clear_current_agency()


def test_vehicle_upsert_one_per_driver(agency):
    d = DriverFactory(agency=agency)
    v = Vehicle(driver=d, registration="LV71 ABC", make="Tesla", model="Model 3", year=2021, colour="Black")
    VehicleService().save(v)
    assert d.vehicle.registration == "LV71 ABC"
    assert d.vehicle.agency_id == agency.id
