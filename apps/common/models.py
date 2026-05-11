import uuid

from django.db import models


class UUIDBaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AgencyScopedModel(UUIDBaseModel, TimestampedModel):
    agency = models.ForeignKey("agencies.Agency", on_delete=models.CASCADE)

    # objects + all_objects declared on abstract base so every subclass inherits both
    from apps.common.managers import AgencyScopedManager
    objects = AgencyScopedManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True
        indexes = [models.Index(fields=["agency"])]
