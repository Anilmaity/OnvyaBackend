import pytest

from apps.agencies.models import Agency, Depot
from apps.common.context import set_current_agency, clear_current_agency
from apps.common.exceptions import CrossAgencyWriteRejected
from apps.common.services import AgencyScopedService


class DepotService(AgencyScopedService):
    model = Depot


@pytest.fixture
def two_agencies(db):
    a = Agency.objects.create(name="A", slug="a")
    b = Agency.objects.create(name="B", slug="b")
    yield a, b
    clear_current_agency()


def test_new_instance_auto_assigns_agency(two_agencies):
    a, _ = two_agencies
    set_current_agency(a)
    depot = Depot(name="A-1")
    DepotService().save(depot)
    depot.refresh_from_db()
    assert depot.agency_id == a.id


def test_update_in_same_agency_succeeds(two_agencies):
    a, _ = two_agencies
    depot = Depot.all_objects.create(agency=a, name="A-1")
    set_current_agency(a)
    depot.name = "A-1-renamed"
    DepotService().save(depot)
    depot.refresh_from_db()
    assert depot.name == "A-1-renamed"


def test_cross_agency_write_rejected(two_agencies):
    a, b = two_agencies
    depot = Depot.all_objects.create(agency=b, name="B-1")
    set_current_agency(a)
    depot.name = "stolen"
    with pytest.raises(CrossAgencyWriteRejected):
        DepotService().save(depot)
