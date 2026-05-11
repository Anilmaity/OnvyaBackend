from django.db import models
from auditlog.registry import auditlog

from apps.common.models import AgencyScopedModel


class Driver(AgencyScopedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING"
        ACTIVE = "ACTIVE"
        RESTING = "RESTING"
        SUSPENDED = "SUSPENDED"
        OFFBOARDED = "OFFBOARDED"

    class LicenceType(models.TextChoices):
        B = "B"
        C1 = "C1"
        C = "C"
        D1 = "D1"
        D = "D"

    user = models.OneToOneField(
        "accounts.AgencyUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="driver_profile"
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=32, blank=True, default="")
    ni_number = models.CharField(max_length=32, blank=True, default="")  # TODO Phase 5: encrypt at rest
    date_of_birth = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    licence_type = models.CharField(max_length=8, choices=LicenceType.choices, blank=True, default="")
    depot = models.ForeignKey("agencies.Depot", on_delete=models.SET_NULL, null=True, blank=True, related_name="drivers")
    flex_enrolled = models.BooleanField(default=False)
    joined_at = models.DateTimeField(null=True, blank=True)
    suspension_reason = models.TextField(blank=True, default="")
    offboard_reason = models.TextField(blank=True, default="")

    class Meta(AgencyScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["agency", "email"], name="driver_unique_email_per_agency"),
        ]
        indexes = AgencyScopedModel.Meta.indexes + [
            models.Index(fields=["agency", "status"]),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class DriverNote(AgencyScopedModel):
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey("accounts.AgencyUser", on_delete=models.SET_NULL, null=True, related_name="driver_notes")
    body = models.TextField()

    class Meta(AgencyScopedModel.Meta):
        ordering = ["-created_at"]


auditlog.register(Driver)
