from apps.documents.models import DriverDocument


def list_documents(*, driver_id=None, kind=None, status=None, expires_before=None):
    qs = DriverDocument.objects.all().select_related("driver").order_by("expires_on", "kind")
    if driver_id:
        qs = qs.filter(driver_id=driver_id)
    if kind:
        qs = qs.filter(kind=kind)
    if status:
        qs = qs.filter(status=status)
    if expires_before:
        qs = qs.filter(expires_on__lte=expires_before)
    return qs
