"""Payments smoke tests using the stub Modulr client."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.agencies.models import Agency
from apps.common.context import clear_current_agency, set_current_agency
from apps.drivers.models import Driver
from apps.invoicing.models import Invoice
from apps.payments.models import (
    AgencyPaymentAccount,
    DriverBankAccount,
    PayRun,
    PayRunItem,
)
from apps.payments.services import (
    IllegalTransition,
    InsufficientFunds,
    MissingPaymentAccount,
    PayRunService,
)


@pytest.fixture
def agency(db):
    a = Agency.objects.create(name="Acme DSP", slug="acme")
    set_current_agency(a)
    yield a
    clear_current_agency()


@pytest.fixture
def issued_invoice(agency):
    driver = Driver.objects.create(
        agency=agency, first_name="Sam", last_name="Driver",
        email="sam@acme.test", status=Driver.Status.ACTIVE,
    )
    DriverBankAccount.objects.create(
        agency=agency, driver=driver, account_holder_name="Sam Driver",
        sort_code="04-00-04", account_number="12345678", is_primary=True,
    )
    period_end = date(2026, 1, 7)
    invoice = Invoice.objects.create(
        agency=agency, driver=driver, number="INV-2026-0001",
        period_start=date(2026, 1, 1), period_end=period_end,
        status=Invoice.Status.ISSUED, subtotal=Decimal("100.00"),
        vat=Decimal("20.00"), total=Decimal("120.00"),
    )
    return invoice


@pytest.fixture
def agency_payment_account(agency):
    return AgencyPaymentAccount.objects.create(
        agency=agency, provider_account_id="A1234567",
        sort_code="04-00-04", account_number="00000001",
        account_name="Acme DSP Ltd",
    )


def test_generate_draft_with_no_invoices_returns_none(agency):
    assert PayRunService().generate_draft(
        period_start=date(2026, 1, 1), period_end=date(2026, 1, 7),
    ) is None


def test_generate_draft_creates_payrun_from_issued_invoices(issued_invoice):
    payrun = PayRunService().generate_draft(
        period_start=date(2026, 1, 1), period_end=date(2026, 1, 7),
    )
    assert payrun is not None
    assert payrun.status == PayRun.Status.DRAFT
    assert payrun.item_count == 1
    assert payrun.total_amount == Decimal("120.00")
    item = payrun.items.get()
    assert item.amount == Decimal("120.00")
    assert item.bank_account is not None
    assert item.reference.startswith("ONV")


def test_approve_blocks_same_user_when_four_eyes_enabled(issued_invoice, settings):
    settings.PAYMENTS_REQUIRE_FOUR_EYES = True
    from django.contrib.auth import get_user_model
    User = get_user_model()
    creator = User.objects.create(agency=issued_invoice.agency, email="a@x.test")
    payrun = PayRunService().generate_draft(
        period_start=date(2026, 1, 1), period_end=date(2026, 1, 7),
        created_by=creator,
    )
    with pytest.raises(IllegalTransition):
        PayRunService().approve(payrun, approver=creator)


def test_submit_requires_payment_account(issued_invoice):
    payrun = PayRunService().generate_draft(
        period_start=date(2026, 1, 1), period_end=date(2026, 1, 7),
    )
    PayRunService().approve(payrun, approver=None)
    with pytest.raises(MissingPaymentAccount):
        PayRunService().submit(payrun, submitter=None)


def test_full_happy_path_with_stub_client(issued_invoice, agency_payment_account):
    payrun = PayRunService().generate_draft(
        period_start=date(2026, 1, 1), period_end=date(2026, 1, 7),
    )
    PayRunService().approve(payrun, approver=None)
    PayRunService().submit(payrun, submitter=None)
    payrun.refresh_from_db()
    assert payrun.status == PayRun.Status.SUBMITTED
    assert payrun.provider_batch_id.startswith("stub-batch-")
    assert payrun.items.get().status == PayRunItem.Status.SUBMITTED


def test_apply_paid_status_updates_invoice_and_rolls_up(
    issued_invoice, agency_payment_account,
):
    svc = PayRunService()
    payrun = svc.generate_draft(
        period_start=date(2026, 1, 1), period_end=date(2026, 1, 7),
    )
    svc.approve(payrun, approver=None)
    svc.submit(payrun, submitter=None)

    item = payrun.items.get()
    svc.apply_item_status(item, status=PayRunItem.Status.PAID,
                          provider_payment_id="P-1")

    item.refresh_from_db()
    payrun.refresh_from_db()
    issued_invoice.refresh_from_db()
    assert item.status == PayRunItem.Status.PAID
    assert payrun.status == PayRun.Status.COMPLETED
    assert issued_invoice.status == Invoice.Status.PAID
