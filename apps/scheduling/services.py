from decimal import Decimal, ROUND_HALF_UP

from django.apps import apps
from django.conf import settings
from django.utils import timezone

from apps.common.services import AgencyScopedService
from apps.scheduling.models import Shift, TimeAdjustment


class IllegalTransition(ValueError):
    pass


class IllegalAdjustment(ValueError):
    pass


DEFAULT_HOURLY_RATE = Decimal(getattr(settings, "DEFAULT_HOURLY_RATE", "15.00"))


def round_quarter(hours: Decimal) -> Decimal:
    """Round to nearest 0.25h."""
    return (Decimal(hours) * 4).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / 4


class ShiftService(AgencyScopedService):
    model = Shift

    _UPDATABLE_STATES = {Shift.Status.SCHEDULED, Shift.Status.IN_PROGRESS}

    def create(self, *, driver, start, end, depot=None, notes=""):
        if end <= start:
            raise IllegalTransition("end must be after start")
        shift = Shift(
            driver=driver, depot=depot, start=start, end=end,
            status=Shift.Status.SCHEDULED, notes=notes,
        )
        return self.save(shift)

    def update(self, shift, **fields):
        if shift.status not in self._UPDATABLE_STATES:
            raise IllegalTransition(f"Cannot edit shift in state {shift.status}")
        for k, v in fields.items():
            setattr(shift, k, v)
        if shift.end <= shift.start:
            raise IllegalTransition("end must be after start")
        return self.save(shift)

    def start_shift(self, shift, at=None):
        if shift.status != Shift.Status.SCHEDULED:
            raise IllegalTransition(f"Cannot start from state {shift.status}")
        shift.status = Shift.Status.IN_PROGRESS
        shift.actual_start = at or timezone.now()
        return self.save(shift)

    def complete(self, shift, actual_start=None, actual_end=None):
        # Idempotent: re-complete just recomputes from given times.
        if shift.status not in (Shift.Status.IN_PROGRESS, Shift.Status.COMPLETED, Shift.Status.SCHEDULED):
            raise IllegalTransition(f"Cannot complete from state {shift.status}")
        shift.actual_start = actual_start or shift.actual_start or shift.start
        shift.actual_end = actual_end or shift.actual_end or shift.end
        if shift.actual_end <= shift.actual_start:
            raise IllegalTransition("actual_end must be after actual_start")
        hours = Decimal((shift.actual_end - shift.actual_start).total_seconds()) / Decimal(3600)
        shift.billable_hours = round_quarter(hours)
        if shift.hourly_rate is None:
            shift.hourly_rate = DEFAULT_HOURLY_RATE
        shift.status = Shift.Status.COMPLETED
        return self.save(shift)

    def cancel(self, shift):
        if shift.status != Shift.Status.SCHEDULED:
            raise IllegalTransition(f"Cannot cancel from state {shift.status}")
        shift.status = Shift.Status.CANCELLED
        return self.save(shift)

    def mark_missed(self, shift):
        if shift.status != Shift.Status.SCHEDULED:
            raise IllegalTransition(f"Cannot mark missed from state {shift.status}")
        shift.status = Shift.Status.MISSED
        return self.save(shift)


class TimeAdjustmentService(AgencyScopedService):
    model = TimeAdjustment

    def _shift_locked_by_invoice(self, shift):
        if not apps.is_installed("apps.invoicing"):
            return False
        from apps.invoicing.models import Invoice, InvoiceLineItem
        return InvoiceLineItem.objects.filter(shift=shift).exclude(
            invoice__status=Invoice.Status.VOID
        ).exists()

    def request(self, *, shift, user, proposed_start, proposed_end, reason):
        if proposed_end <= proposed_start:
            raise IllegalAdjustment("proposed_end must be after proposed_start")
        if self._shift_locked_by_invoice(shift):
            raise IllegalAdjustment("Shift is already invoiced; cannot adjust")
        adj = TimeAdjustment(
            shift=shift, requested_by=user,
            proposed_start=proposed_start, proposed_end=proposed_end,
            reason=reason, state=TimeAdjustment.State.PENDING,
        )
        return self.save(adj)

    def approve(self, adj, user, decision_note=""):
        if adj.state != TimeAdjustment.State.PENDING:
            raise IllegalAdjustment(f"Cannot approve from state {adj.state}")
        if self._shift_locked_by_invoice(adj.shift):
            raise IllegalAdjustment("Shift is already invoiced; cannot adjust")
        shift = adj.shift
        shift.actual_start = adj.proposed_start
        shift.actual_end = adj.proposed_end
        if shift.status == Shift.Status.COMPLETED:
            # Recompute billable hours but keep rate snapshot
            hours = Decimal((shift.actual_end - shift.actual_start).total_seconds()) / Decimal(3600)
            shift.billable_hours = round_quarter(hours)
        ShiftService().save(shift)
        adj.state = TimeAdjustment.State.APPROVED
        adj.decided_by = user
        adj.decided_at = timezone.now()
        adj.decision_note = decision_note or ""
        return self.save(adj)

    def reject(self, adj, user, decision_note):
        if adj.state != TimeAdjustment.State.PENDING:
            raise IllegalAdjustment(f"Cannot reject from state {adj.state}")
        adj.state = TimeAdjustment.State.REJECTED
        adj.decided_by = user
        adj.decided_at = timezone.now()
        adj.decision_note = decision_note
        return self.save(adj)
