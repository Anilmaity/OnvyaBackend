from apps.drivers.models import Driver


def list_drivers(*, status=None, depot_id=None, flex_enrolled=None, search=None):
    qs = Driver.objects.all()
    if status:
        qs = qs.filter(status=status)
    if depot_id:
        qs = qs.filter(depot_id=depot_id)
    if flex_enrolled is not None:
        qs = qs.filter(flex_enrolled=flex_enrolled)
    if search:
        qs = qs.filter(
            first_name__icontains=search
        ) | qs.filter(last_name__icontains=search) | qs.filter(email__icontains=search)
    return qs.order_by("last_name", "first_name")
