from apps.common.context import get_current_agency
from apps.common.exceptions import CrossAgencyWriteRejected


class AgencyScopedService:
    """Base class — every mutation goes through `service.save()` rather than `instance.save()`."""

    model = None

    def save(self, instance):
        current = get_current_agency()
        if current is None:
            raise CrossAgencyWriteRejected("No agency context set; refusing to write.")
        if instance._state.adding:
            if instance.agency_id is None:
                instance.agency = current
            elif str(instance.agency_id) != str(current.id):
                raise CrossAgencyWriteRejected(
                    f"New {type(instance).__name__} has agency_id != current agency."
                )
        else:
            if str(instance.agency_id) != str(current.id):
                raise CrossAgencyWriteRejected(
                    f"Update on {type(instance).__name__} crosses agency boundary."
                )
        instance.save()
        return instance
