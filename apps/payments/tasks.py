"""Background reconciliation for payments.

Webhooks are authoritative when they arrive — these tasks are a
belt-and-braces safety net for delivery gaps. They run per-tenant and
must set the agency context before any ORM read or write.
"""

from celery import shared_task
from django.utils import timezone

from apps.agencies.models import Agency
from apps.common.context import agency_context
from apps.payments.models import AgencyPaymentAccount, PayRun
from apps.payments.modulr import ModulrError, get_modulr_client


@shared_task
def sync_agency_balances():
    """Refresh ``AgencyPaymentAccount.last_known_balance`` for every active
    agency. Designed to run every ~5 min from Celery Beat."""
    client = get_modulr_client()
    for agency in Agency.objects.filter(is_active=True):
        with agency_context(agency):
            account = AgencyPaymentAccount.objects.filter(is_active=True).first()
            if account is None:
                continue
            try:
                balance = client.get_account_balance(account.provider_account_id)
            except ModulrError:
                continue
            account.last_known_balance = balance.available
            account.last_balance_synced_at = timezone.now()
            account.save(update_fields=[
                "last_known_balance", "last_balance_synced_at", "updated_at",
            ])


@shared_task
def reconcile_submitted_payruns():
    """Look at any PayRun in SUBMITTED state older than the staleness
    threshold and re-roll-up from item statuses, in case webhooks were
    missed. Re-fetching from Modulr is left to a future task —
    ``apply_item_status`` already handles the actual mutation."""
    from apps.payments.services import PayRunService

    cutoff = timezone.now() - timezone.timedelta(minutes=15)
    for agency in Agency.objects.filter(is_active=True):
        with agency_context(agency):
            stale = PayRun.objects.filter(
                status=PayRun.Status.SUBMITTED, submitted_at__lt=cutoff,
            )
            for payrun in stale:
                PayRunService()._roll_up_payrun(payrun)
