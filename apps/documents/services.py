from datetime import timedelta

from django.utils import timezone

from apps.common.services import AgencyScopedService
from apps.documents.models import DriverDocument


EXPIRING_WINDOW_DAYS = 30


def compute_status(expires_on):
    if expires_on is None:
        return DriverDocument.Status.MISSING
    today = timezone.localdate()
    if expires_on < today:
        return DriverDocument.Status.EXPIRED
    if expires_on <= today + timedelta(days=EXPIRING_WINDOW_DAYS):
        return DriverDocument.Status.EXPIRING
    return DriverDocument.Status.VALID


class DocumentService(AgencyScopedService):
    model = DriverDocument

    def upsert(self, *, driver, kind, reference="", issued_on=None, expires_on=None, notes=""):
        doc = DriverDocument.objects.filter(driver=driver, kind=kind).first()
        if doc is None:
            doc = DriverDocument(driver=driver, kind=kind)
        doc.reference = reference or ""
        doc.issued_on = issued_on
        doc.expires_on = expires_on
        doc.notes = notes or ""
        doc.status = compute_status(expires_on)
        return self.save(doc)

    @classmethod
    def recompute_all(cls, agency=None):
        qs = DriverDocument.objects.all()
        if agency is not None:
            qs = qs.filter(agency=agency)
        changed = 0
        for doc in qs:
            new = compute_status(doc.expires_on)
            if new != doc.status:
                doc.status = new
                doc.save(update_fields=["status", "updated_at"])
                changed += 1
        return changed
