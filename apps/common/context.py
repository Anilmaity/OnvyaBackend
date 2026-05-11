from contextlib import contextmanager
from contextvars import ContextVar

_current_agency: ContextVar = ContextVar("current_agency", default=None)


def set_current_agency(agency):
    _current_agency.set(agency)


def get_current_agency():
    return _current_agency.get()


def clear_current_agency():
    _current_agency.set(None)


@contextmanager
def agency_context(agency):
    token = _current_agency.set(agency)
    try:
        yield
    finally:
        _current_agency.reset(token)
