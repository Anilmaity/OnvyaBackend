from django.db import models
from auditlog.registry import auditlog

from apps.common.models import AgencyScopedModel


class Course(AgencyScopedModel):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    validity_months = models.PositiveIntegerField(null=True, blank=True)
    is_required = models.BooleanField(default=False)

    class Meta(AgencyScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["agency", "name"], name="course_unique_name_per_agency",
            ),
        ]


class Completion(AgencyScopedModel):
    class Status(models.TextChoices):
        VALID = "VALID"
        EXPIRING = "EXPIRING"
        EXPIRED = "EXPIRED"

    driver = models.ForeignKey("drivers.Driver", on_delete=models.CASCADE, related_name="training")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="completions")
    completed_on = models.DateField()
    expires_on = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.VALID)
    certificate_reference = models.CharField(max_length=128, blank=True, default="")
    notes = models.TextField(blank=True, default="")

    class Meta(AgencyScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["agency", "driver", "course"],
                name="completion_unique_per_driver_course",
            ),
        ]
        indexes = AgencyScopedModel.Meta.indexes + [
            models.Index(fields=["agency", "status", "expires_on"]),
        ]


auditlog.register(Course)
auditlog.register(Completion)
