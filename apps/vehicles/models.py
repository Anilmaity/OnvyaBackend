from django.db import models
from auditlog.registry import auditlog

from apps.common.models import AgencyScopedModel


class Vehicle(AgencyScopedModel):
    driver = models.OneToOneField(
        "drivers.Driver", on_delete=models.CASCADE, related_name="vehicle"
    )
    registration = models.CharField(max_length=16, blank=True, default="")
    make = models.CharField(max_length=64, blank=True, default="")
    model = models.CharField(max_length=64, blank=True, default="")
    year = models.PositiveIntegerField(null=True, blank=True)
    colour = models.CharField(max_length=32, blank=True, default="")

    def __str__(self):
        return f"{self.registration} ({self.make} {self.model})"


auditlog.register(Vehicle)
