from django.db import models
from auditlog.registry import auditlog

from apps.common.models import AgencyScopedModel


class DriverDocument(AgencyScopedModel):
    class Kind(models.TextChoices):
        DRIVING_LICENCE = "DRIVING_LICENCE"
        RIGHT_TO_WORK = "RIGHT_TO_WORK"
        INSURANCE = "INSURANCE"
        MOT = "MOT"
        DBS = "DBS"
        CPC = "CPC"

    class Status(models.TextChoices):
        VALID = "VALID"
        EXPIRING = "EXPIRING"
        EXPIRED = "EXPIRED"
        MISSING = "MISSING"

    driver = models.ForeignKey(
        "drivers.Driver", on_delete=models.CASCADE, related_name="documents",
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    reference = models.CharField(max_length=128, blank=True, default="")
    issued_on = models.DateField(null=True, blank=True)
    expires_on = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.MISSING)
    notes = models.TextField(blank=True, default="")

    class Meta(AgencyScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["agency", "driver", "kind"],
                name="document_unique_kind_per_driver",
            ),
        ]
        indexes = AgencyScopedModel.Meta.indexes + [
            models.Index(fields=["agency", "status", "expires_on"]),
        ]


auditlog.register(DriverDocument)
