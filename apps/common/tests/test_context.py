import pytest

from apps.common.context import (
    get_current_agency,
    set_current_agency,
    clear_current_agency,
    agency_context,
)


class _FakeAgency:
    def __init__(self, id):
        self.id = id


def test_no_agency_set_returns_none():
    clear_current_agency()
    assert get_current_agency() is None


def test_set_and_get():
    a = _FakeAgency(1)
    set_current_agency(a)
    assert get_current_agency() is a
    clear_current_agency()


def test_clear():
    set_current_agency(_FakeAgency(1))
    clear_current_agency()
    assert get_current_agency() is None


def test_context_manager_restores():
    outer = _FakeAgency(1)
    inner = _FakeAgency(2)
    set_current_agency(outer)
    with agency_context(inner):
        assert get_current_agency() is inner
    assert get_current_agency() is outer
    clear_current_agency()
