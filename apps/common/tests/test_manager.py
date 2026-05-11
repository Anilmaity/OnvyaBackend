import pytest
from django.test.utils import override_settings

from apps.agencies.models import Agency, Depot
from apps.common.context import set_current_agency, clear_current_agency, agency_context
from apps.common.exceptions import AgencyContextMissing


@pytest.fixture
def two_agencies(db):
    a = Agency.objects.create(name="A", slug="a")
    b = Agency.objects.create(name="B", slug="b")
    yield a, b
    clear_current_agency()


def test_manager_auto_filters(two_agencies):
    a, b = two_agencies
    Depot.all_objects.create(agency=a, name="A-depot")
    Depot.all_objects.create(agency=b, name="B-depot")
    set_current_agency(a)
    names = list(Depot.objects.values_list("name", flat=True))
    assert names == ["A-depot"]


def test_all_objects_returns_unfiltered(two_agencies):
    a, b = two_agencies
    Depot.all_objects.create(agency=a, name="A-depot")
    Depot.all_objects.create(agency=b, name="B-depot")
    set_current_agency(a)
    names = set(Depot.all_objects.values_list("name", flat=True))
    assert names == {"A-depot", "B-depot"}


def test_strict_mode_raises_without_agency(two_agencies):
    a, _ = two_agencies
    Depot.all_objects.create(agency=a, name="A-depot")
    clear_current_agency()
    with pytest.raises(AgencyContextMissing):
        list(Depot.objects.all())


@override_settings(AGENCY_SCOPE_STRICT=False)
def test_non_strict_returns_all_without_agency(two_agencies):
    a, b = two_agencies
    Depot.all_objects.create(agency=a, name="A-depot")
    Depot.all_objects.create(agency=b, name="B-depot")
    clear_current_agency()
    assert Depot.objects.count() == 2


def test_context_manager_scopes_query(two_agencies):
    a, b = two_agencies
    Depot.all_objects.create(agency=a, name="A-depot")
    Depot.all_objects.create(agency=b, name="B-depot")
    with agency_context(b):
        names = list(Depot.objects.values_list("name", flat=True))
    assert names == ["B-depot"]
