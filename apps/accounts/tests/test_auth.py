import pytest
from graphene.test import Client

from apps.audit.models import LoginEvent
from apps.accounts.factories import AgencyUserFactory
from config.schema import schema


@pytest.fixture
def user(db):
    return AgencyUserFactory(email="u@a.test", password="demo1234")


def _exec(query, context=None, variables=None):
    return Client(schema).execute(query, context=context, variables=variables)


LOGIN = """
mutation($e: String!, $p: String!) {
  login(email: $e, password: $p) {
    __typename
    ... on AuthPayload { accessToken refreshToken user { email } }
    ... on ValidationError { fieldErrors { field message } }
  }
}
"""


class _Req:
    META = {"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "test"}


def test_login_happy(user):
    result = _exec(LOGIN, context=_Req(), variables={"e": "u@a.test", "p": "demo1234"})
    assert "errors" not in result
    data = result["data"]["login"]
    assert data["__typename"] == "AuthPayload"
    assert data["user"]["email"] == "u@a.test"
    assert LoginEvent.objects.filter(success=True, email_attempted="u@a.test").exists()


def test_login_bad_password(user):
    result = _exec(LOGIN, context=_Req(), variables={"e": "u@a.test", "p": "wrong"})
    data = result["data"]["login"]
    assert data["__typename"] == "ValidationError"
    assert LoginEvent.objects.filter(success=False, email_attempted="u@a.test").exists()


def test_login_inactive_user(db):
    AgencyUserFactory(email="x@a.test", password="demo1234", is_active=False)
    result = _exec(LOGIN, context=_Req(), variables={"e": "x@a.test", "p": "demo1234"})
    data = result["data"]["login"]
    assert data["__typename"] == "ValidationError"
    assert LoginEvent.objects.filter(success=False, email_attempted="x@a.test").exists()
