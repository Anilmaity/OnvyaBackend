import re

import pytest

from apps.agencies.models import Agency
from apps.accounts.models import AgencyUser, Role
from apps.drivers.models import Driver
from apps.drivers.services import DriverService
from apps.common.context import set_current_agency, clear_current_agency


@pytest.fixture
def agency_ctx(db):
    agency = Agency.objects.create(name="A", slug="a")
    set_current_agency(agency)
    Role.objects.create(agency=agency, name="Driver")
    yield agency
    clear_current_agency()


def test_create_generates_6_digit_code(agency_ctx):
    d = DriverService().create(first_name="A", last_name="B", email="ab@a.test")
    assert re.fullmatch(r"\d{6}", d.registration_code)


def test_create_makes_disabled_login_with_driver_role(agency_ctx):
    d = DriverService().create(first_name="A", last_name="B", email="ab@a.test")
    assert d.user is not None
    assert d.user.is_active is False
    assert d.user.has_usable_password() is False
    assert d.user.user_roles.filter(role__name="Driver").exists()


def test_create_links_existing_user_not_duplicate(agency_ctx):
    existing = AgencyUser(
        agency=agency_ctx, email="ab@a.test",
        first_name="A", last_name="B", is_active=False,
    )
    existing.set_unusable_password()
    existing.save()
    d = DriverService().create(first_name="A", last_name="B", email="AB@a.test")
    assert d.user_id == existing.id
    assert AgencyUser.all_objects.filter(agency=agency_ctx, email="ab@a.test").count() == 1


def test_create_sends_email_with_code(agency_ctx):
    from django.core import mail
    mail.outbox.clear()
    d = DriverService().create(first_name="A", last_name="B", email="ab@a.test")
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.to == ["ab@a.test"]
    assert d.registration_code in msg.body


def test_driver_type_exposes_code_and_registered(agency_ctx):
    from graphene.test import Client
    from apps.accounts.models import AgencyUser, Role, Permission, RolePermission, UserRole
    from config.schema import schema

    d = DriverService().create(first_name="A", last_name="B", email="ab@a.test")

    reader = AgencyUser(agency=agency_ctx, email="reader@a.test", is_active=True)
    reader.set_password("x")
    reader.save()
    role = Role.objects.create(agency=agency_ctx, name="Reader")
    perm, _ = Permission.objects.get_or_create(code="drivers.read")
    RolePermission.objects.create(role=role, permission=perm)
    UserRole.objects.create(user=reader, role=role)

    class Req:
        pass
    req = Req()
    req.user = reader
    req.current_agency = agency_ctx

    q = f'query {{ driver(id: "{d.id}") {{ registrationCode registered }} }}'
    result = Client(schema).execute(q, context=req)
    assert result.get("errors") is None
    assert result["data"]["driver"]["registrationCode"] == d.registration_code
    assert result["data"]["driver"]["registered"] is False
