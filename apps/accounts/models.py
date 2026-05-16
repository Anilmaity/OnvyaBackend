import uuid

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from apps.common.models import AgencyScopedModel, UUIDBaseModel, TimestampedModel
from .managers import AgencyUserManager


class AgencyUser(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agency = models.ForeignKey("agencies.Agency", on_delete=models.CASCADE, related_name="users")
    email = models.EmailField()
    first_name = models.CharField(max_length=100, blank=True, default="")
    last_name = models.CharField(max_length=100, blank=True, default="")
    phone = models.CharField(max_length=32, blank=True, default="")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = AgencyUserManager()
    all_objects = BaseUserManager()  # truly unscoped — used at login (no agency context yet) and createsuperuser

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["agency", "email"], name="user_unique_email_per_agency"),
        ]
        indexes = [models.Index(fields=["agency", "email"])]
        default_manager_name = "all_objects"

    def __str__(self):
        return f"{self.email} ({self.agency_id})"


class Role(AgencyScopedModel):
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True, default="")
    is_system = models.BooleanField(default=False)

    class Meta(AgencyScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["agency", "name"], name="role_unique_name_per_agency"),
        ]

    def __str__(self):
        return self.name


class Permission(UUIDBaseModel, TimestampedModel):
    code = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True, default="")

    def __str__(self):
        return self.code


class RolePermission(UUIDBaseModel, TimestampedModel):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="role_permissions")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["role", "permission"], name="rolepermission_unique"),
        ]


class UserRole(UUIDBaseModel, TimestampedModel):
    user = models.ForeignKey(AgencyUser, on_delete=models.CASCADE, related_name="user_roles")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="user_roles")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "role"], name="userrole_unique"),
        ]
