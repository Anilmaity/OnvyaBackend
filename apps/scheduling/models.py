import uuid

from django.db import models
from auditlog.registry import auditlog

from apps.common.models import AgencyScopedModel


class Shift(AgencyScopedModel):
    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED"
        IN_PROGRESS = "IN_PROGRESS"
        COMPLETED = "COMPLETED"
        MISSED = "MISSED"
        CANCELLED = "CANCELLED"

    driver = models.ForeignKey(
        "drivers.Driver", on_delete=models.PROTECT, related_name="shifts"
    )
    depot = models.ForeignKey(
        "agencies.Depot", on_delete=models.SET_NULL, null=True, blank=True, related_name="shifts"
    )
    start = models.DateTimeField()
    end = models.DateTimeField()
    actual_start = models.DateTimeField(null=True, blank=True)
    actual_end = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SCHEDULED)
    notes = models.TextField(blank=True, default="")
    billable_hours = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    hourly_rate = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    template_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta(AgencyScopedModel.Meta):
        indexes = AgencyScopedModel.Meta.indexes + [
            models.Index(fields=["agency", "driver", "start"]),
            models.Index(fields=["agency", "status", "start"]),
        ]


class TimeAdjustment(AgencyScopedModel):
    class State(models.TextChoices):
        PENDING = "PENDING"
        APPROVED = "APPROVED"
        REJECTED = "REJECTED"

    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name="adjustments")
    requested_by = models.ForeignKey(
        "accounts.AgencyUser", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="requested_adjustments",
    )
    decided_by = models.ForeignKey(
        "accounts.AgencyUser", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="decided_adjustments",
    )
    proposed_start = models.DateTimeField()
    proposed_end = models.DateTimeField()
    reason = models.TextField()
    state = models.CharField(max_length=16, choices=State.choices, default=State.PENDING)
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True, default="")


auditlog.register(Shift)
auditlog.register(TimeAdjustment)
