from apps.payments.models import PayRun, PayRunItem


def list_payruns(*, status=None, period_start_after=None, period_end_before=None):
    qs = (
        PayRun.objects.all()
        .prefetch_related("items")
        .order_by("-period_end", "-created_at")
    )
    if status:
        qs = qs.filter(status=status)
    if period_start_after:
        qs = qs.filter(period_start__gte=period_start_after)
    if period_end_before:
        qs = qs.filter(period_end__lte=period_end_before)
    return qs


def list_payrun_items(payrun_id):
    return (
        PayRunItem.objects.filter(payrun_id=payrun_id)
        .select_related("driver", "bank_account", "invoice")
        .order_by("driver__last_name")
    )
