"""Modulr webhook receiver.

Modulr POSTs JSON events (``payment.outbound.completed``,
``payment.outbound.failed``, ``payment.outbound.returned`` and friends) with
an HMAC-SHA512 signature in the ``x-mod-signature`` header. We must verify
the signature against the raw body before doing anything else.

Tenant resolution: Modulr does not know our agency IDs, but the payments
each carry an ``externalReference`` we set when submitting the batch —
the ``PayRunItem.idempotency_key``. That lookup gets us back to the
agency so we can scope the rest of the work.
"""

import json

from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.common.context import agency_context
from apps.payments.models import PaymentStatusEvent, PayRunItem
from apps.payments.modulr import verify_webhook_signature
from apps.payments.services import PayRunService


# Map Modulr event names to our terminal item statuses.
_STATUS_MAP = {
    "payment.outbound.completed": PayRunItem.Status.PAID,
    "payment.outbound.failed": PayRunItem.Status.FAILED,
    "payment.outbound.returned": PayRunItem.Status.RETURNED,
}


@csrf_exempt
@require_POST
def modulr_webhook(request):
    signature = request.headers.get("x-mod-signature", "")
    if not verify_webhook_signature(request.body, signature):
        return HttpResponse(status=401)

    try:
        event = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return HttpResponseBadRequest("invalid json")

    event_type = event.get("type", "")
    provider_event_id = str(event.get("id", ""))
    data = event.get("data", {}) or {}
    external_ref = data.get("externalReference", "")
    provider_payment_id = str(data.get("id", ""))

    if not external_ref:
        # Batch-level or account-level event; record and ack.
        PaymentStatusEvent.objects.create(
            agency_id=_resolve_agency_for_batch(data),
            event_type=event_type,
            provider_event_id=provider_event_id,
            payload=event,
        )
        return JsonResponse({"ok": True})

    item = (
        PayRunItem.all_objects
        .select_related("payrun", "agency")
        .filter(idempotency_key=external_ref)
        .first()
    )
    if item is None:
        return JsonResponse({"ok": True, "ignored": True})

    with agency_context(item.agency):
        PaymentStatusEvent.objects.create(
            agency=item.agency,
            item=item,
            payrun=item.payrun,
            event_type=event_type,
            provider_event_id=provider_event_id,
            payload=event,
        )
        new_status = _STATUS_MAP.get(event_type)
        if new_status:
            PayRunService().apply_item_status(
                item,
                status=new_status,
                provider_payment_id=provider_payment_id,
                failure_reason=str(data.get("failureReason", "")),
                paid_at=timezone.now() if new_status == PayRunItem.Status.PAID else None,
            )

    return JsonResponse({"ok": True})


def _resolve_agency_for_batch(data):
    """Best-effort: a batch event carries our batch idempotency key as
    ``externalReference`` at the batch level too. Falls back to None if
    we can't tie it to a known PayRun."""
    from apps.payments.models import PayRun

    batch_ref = data.get("externalReference") or data.get("id")
    if not batch_ref:
        return None
    pr = PayRun.all_objects.filter(
        idempotency_key=batch_ref,
    ).values_list("agency_id", flat=True).first()
    return pr
