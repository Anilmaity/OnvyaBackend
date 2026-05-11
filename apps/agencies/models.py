import uuid

from django.db import models

from apps.common.models import AgencyScopedModel


class Agency(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, max_length=80)
    timezone = models.CharField(max_length=64, default="Europe/London")
    primary_color = models.CharField(max_length=9, default="#004B44")
    logo = models.ImageField(upload_to="agencies/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Depot(AgencyScopedModel):
    name = models.CharField(max_length=200)
    address = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta(AgencyScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["agency", "name"], name="depot_unique_name_per_agency"),
        ]

    def __str__(self):
        return self.name
