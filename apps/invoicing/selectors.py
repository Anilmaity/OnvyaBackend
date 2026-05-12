from apps.invoicing.models import Invoice


def list_invoices(*, driver_id=None, status=None, period_start_after=None, period_end_before=None):
    qs = Invoice.objects.all().select_related("driver").prefetch_related("line_items").order_by("-period_end")
    if driver_id:
        qs = qs.filter(driver_id=driver_id)
    if status:
        qs = qs.filter(status=status)
    if period_start_after:
        qs = qs.filter(period_start__gte=period_start_after)
    if period_end_before:
        qs = qs.filter(period_end__lte=period_end_before)
    return qs
