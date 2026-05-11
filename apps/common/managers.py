from django.conf import settings
from django.db import models

from apps.common.context import get_current_agency
from apps.common.exceptions import AgencyContextMissing


class AgencyScopedQuerySet(models.QuerySet):
    def for_agency(self, agency):
        return self.filter(agency=agency)


class AgencyScopedManager(models.Manager.from_queryset(AgencyScopedQuerySet)):
    """Auto-filters every query by the current agency loaded from request context."""

    def get_queryset(self):
        qs = super().get_queryset()
        agency = get_current_agency()
        if agency is None:
            if getattr(settings, "AGENCY_SCOPE_STRICT", True):
                raise AgencyContextMissing(
                    f"Query on {self.model.__name__} ran with no agency context. "
                    "Use Model.all_objects for system tasks or set agency_context()."
                )
            return qs
        return qs.filter(agency=agency)
