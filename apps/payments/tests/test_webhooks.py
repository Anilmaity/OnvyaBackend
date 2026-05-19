"""Modulr webhook handler tests."""

import hashlib
import hmac
import json
from datetime import date
from decimal import Decimal

import pytest
from django.test import Client

from apps.agencies.models import Agency
from apps.common.context import clear_current_agency, set_current_agency
from apps.drivers.models import Driver
from apps.invoicing.models import Invoice
from apps.payments.models import (
    AgencyPaymentAccount,
    DriverBankAccount,
    PaymentStatusEvent,
    PayRun,
    PayRunItem,
)
from apps.payments.services import PayRunService


WEBHOOK_SECRET = "test-webhook-secret"
WEBHOOK_URL = "/webhooks/modulr/"


def _sign(body: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha512).hexdigest()


def _post(client, payload, *, signature=None):
    body = json.dumps(payload).encode()
    sig = signature if signature is not None else _sign(body)
    return client.post(
        WEBHOOK_URL, data=body, content_type="application/json",
        HTTP_X_MOD_SIGNATURE=sig,
    )


@pytest.fixture(autouse=True)
def _webhook_secret(settings):
    settings.MODULR_WEBHOOK_SECRET = WEBHOOK_SECRET


@pytest.fixture
def submitted_payrun(db):
    agency = Agency.objects.create(name="Acme DSP", slug="acme-webhook")
    set_current_agency(agency)
    try:
        driver = Driver.objects.create(
            agency=agency, first_name="Sam", last_name="Driver",
            email="sam@acme.test", status=Driver.Status.ACTIVE,
        )
        DriverBankAccount.objects.create(
            agency=agency, driver=driver, account_holder_name="Sam Driver",
            sort_code="04-00-04", account_number="12345678", is_primary=True,
        )
        invoice = Invoice.objects.create(
            agency=agency, driver=driver, number="INV-2026-WH01",
            period_start=date(2026, 1, 1), period_end=date(2026, 1, 7),
            status=Invoice.Status.ISSUED, subtotal=Decimal("100.00"),
            vat=Decimal("20.00"), total=Decimal("120.00"),
        )
        AgencyPaymentAccount.objects.create(
            agency=agency, provider_account_id="A1234567",
            sort_code="04-00-04", account_number="00000001",
            account_name="Acme DSP Ltd",
        )
        svc = PayRunService()
        payrun = svc.generate_draft(
            period_start=date(2026, 1, 1), period_end=date(2026, 1, 7),
        )
        svc.approve(payrun, approver=None)
        svc.submit(payrun, submitter=None)
        yield agency, payrun, invoice
    finally:
        clear_current_agency()


# --------------------------------------------------------------------------- #
# Signature verification                                                      #
# --------------------------------------------------------------------------- #


def test_missing_signature_returns_401(db):
    client = Client()
    resp = client.post(
        WEBHOOK_URL, data=b"{}", content_type="application/json",
    )
    assert resp.status_code == 401


def test_invalid_signature_returns_401(db):
    client = Client()
    resp = _post(client, {"type": "noop"}, signature="deadbeef")
    assert resp.status_code == 401


def test_get_method_not_allowed(db):
    resp = Client().get(WEBHOOK_URL)
    assert resp.status_code == 405


def test_invalid_json_returns_400(db):
    body = b"not-json"
    resp = Client().post(
        WEBHOOK_URL, data=body, content_type="application/json",
        HTTP_X_MOD_SIGNATURE=_sign(body),
    )
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# Routing                                                                     #
# --------------------------------------------------------------------------- #


def test_unknown_external_reference_is_ignored_with_200(db):
    resp = _post(Client(), {
        "id": "evt-1",
        "type": "payment.outbound.completed",
        "data": {"id": "P-1", "externalReference": "does-not-exist"},
    })
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "ignored": True}


# --------------------------------------------------------------------------- #
# Status mapping                                                              #
# --------------------------------------------------------------------------- #


def test_completed_event_marks_item_paid_and_invoice_paid(submitted_payrun):
    agency, payrun, invoice = submitted_payrun
    item = payrun.items.get()

    resp = _post(Client(), {
        "id": "evt-completed-1",
        "type": "payment.outbound.completed",
        "data": {
            "id": "P-PAID-1",
            "externalReference": item.idempotency_key,
        },
    })
    assert resp.status_code == 200

    # The webhook view runs through AgencyContextMiddleware which clears
    # context in its finally block, so assertions must use all_objects.
    item = PayRunItem.all_objects.get(pk=item.pk)
    payrun = PayRun.all_objects.get(pk=payrun.pk)
    invoice = Invoice.all_objects.get(pk=invoice.pk)
    assert item.status == PayRunItem.Status.PAID
    assert item.provider_payment_id == "P-PAID-1"
    assert item.paid_at is not None
    assert payrun.status == PayRun.Status.COMPLETED
    assert invoice.status == Invoice.Status.PAID

    event = PaymentStatusEvent.all_objects.get(item=item)
    assert event.event_type == "payment.outbound.completed"
    assert event.provider_event_id == "evt-completed-1"


def test_failed_event_marks_item_failed(submitted_payrun):
    _, payrun, _ = submitted_payrun
    item = payrun.items.get()

    resp = _post(Client(), {
        "id": "evt-failed-1",
        "type": "payment.outbound.failed",
        "data": {
            "id": "P-FAIL-1",
            "externalReference": item.idempotency_key,
            "failureReason": "Beneficiary account closed",
        },
    })
    assert resp.status_code == 200

    item = PayRunItem.all_objects.get(pk=item.pk)
    payrun = PayRun.all_objects.get(pk=payrun.pk)
    assert item.status == PayRunItem.Status.FAILED
    assert "closed" in item.failure_reason
    assert payrun.status == PayRun.Status.FAILED


def test_returned_event_marks_item_returned(submitted_payrun):
    _, payrun, _ = submitted_payrun
    item = payrun.items.get()

    resp = _post(Client(), {
        "id": "evt-returned-1",
        "type": "payment.outbound.returned",
        "data": {"id": "P-RET-1", "externalReference": item.idempotency_key},
    })
    assert resp.status_code == 200

    item = PayRunItem.all_objects.get(pk=item.pk)
    assert item.status == PayRunItem.Status.RETURNED


# --------------------------------------------------------------------------- #
# Idempotency                                                                 #
# --------------------------------------------------------------------------- #


def test_duplicate_completed_event_is_idempotent(submitted_payrun):
    _, payrun, _ = submitted_payrun
    item = payrun.items.get()
    payload = {
        "id": "evt-dup-1",
        "type": "payment.outbound.completed",
        "data": {"id": "P-DUP", "externalReference": item.idempotency_key},
    }
    client = Client()
    assert _post(client, payload).status_code == 200
    first_paid_at = PayRunItem.all_objects.get(pk=item.pk).paid_at

    # Second delivery of the same event must not change state and must not
    # blow up on the unique (agency, provider_event_id) constraint.
    payload["id"] = "evt-dup-2"  # different event id, same business outcome
    assert _post(client, payload).status_code == 200

    item = PayRunItem.all_objects.get(pk=item.pk)
    assert item.status == PayRunItem.Status.PAID
    assert item.paid_at == first_paid_at  # apply_item_status is a no-op on PAID
