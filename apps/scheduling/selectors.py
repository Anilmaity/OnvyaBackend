from apps.scheduling.models import Shift, TimeAdjustment


def list_shifts(*, driver_id=None, depot_id=None, status=None, start_after=None, start_before=None):
    qs = Shift.objects.all().select_related("driver", "depot").order_by("start")
    if driver_id:
        qs = qs.filter(driver_id=driver_id)
    if depot_id:
        qs = qs.filter(depot_id=depot_id)
    if status:
        qs = qs.filter(status=status)
    if start_after:
        qs = qs.filter(start__gte=start_after)
    if start_before:
        qs = qs.filter(start__lte=start_before)
    return qs


def list_shifts_for_billing(*, driver, period_start, period_end):
    """COMPLETED shifts in date range whose actual_end falls within [period_start, period_end]."""
    return Shift.objects.filter(
        driver=driver,
        status=Shift.Status.COMPLETED,
        actual_end__date__gte=period_start,
        actual_end__date__lte=period_end,
    ).order_by("actual_end")


def list_time_adjustments(*, shift_id=None, state=None):
    qs = TimeAdjustment.objects.all().select_related("shift", "requested_by", "decided_by").order_by("-created_at")
    if shift_id:
        qs = qs.filter(shift_id=shift_id)
    if state:
        qs = qs.filter(state=state)
    return qs
