import uuid

from django.db import models


class LoginEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "accounts.AgencyUser",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="login_events",
    )
    agency = models.ForeignKey(
        "agencies.Agency",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="login_events",
    )
    email_attempted = models.EmailField()
    success = models.BooleanField()
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["email_attempted", "created_at"]),
            models.Index(fields=["user", "created_at"]),
        ]
        ordering = ["-created_at"]
