import pytest
from django.test import RequestFactory
from rest_framework_simplejwt.tokens import RefreshToken

from apps.agencies.models import Agency
from apps.accounts.models import AgencyUser
from apps.common.context import get_current_agency, clear_current_agency
from apps.common.middleware import AgencyContextMiddleware


@pytest.fixture
def user(db):
    a = Agency.objects.create(name="A", slug="a")
    u = AgencyUser(email="u@a.test", agency=a)
    u.set_password("x")
    u.save()
    yield u
    clear_current_agency()


def _get_response(req):
    return "ok"


def test_middleware_sets_agency_from_jwt(user):
    refresh = RefreshToken.for_user(user)
    refresh["agency_id"] = str(user.agency_id)
    access = str(refresh.access_token)

    req = RequestFactory().get("/graphql/", HTTP_AUTHORIZATION=f"Bearer {access}")
    seen = {}

    def downstream(request):
        seen["agency"] = get_current_agency()
        return "ok"

    mw = AgencyContextMiddleware(downstream)
    mw(req)

    assert seen["agency"].id == user.agency_id


def test_middleware_clears_after_request(user):
    refresh = RefreshToken.for_user(user)
    refresh["agency_id"] = str(user.agency_id)
    access = str(refresh.access_token)

    req = RequestFactory().get("/graphql/", HTTP_AUTHORIZATION=f"Bearer {access}")
    AgencyContextMiddleware(_get_response)(req)
    assert get_current_agency() is None


def test_middleware_no_token_leaves_context_unset(db):
    req = RequestFactory().get("/graphql/")
    AgencyContextMiddleware(_get_response)(req)
    assert get_current_agency() is None


def test_middleware_invalid_token_returns_401(db):
    req = RequestFactory().get("/graphql/", HTTP_AUTHORIZATION="Bearer not-a-real-token")
    response = AgencyContextMiddleware(_get_response)(req)
    assert getattr(response, "status_code", None) == 401
