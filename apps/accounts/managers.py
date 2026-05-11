from django.contrib.auth.base_user import BaseUserManager

from apps.common.context import get_current_agency
from apps.common.managers import AgencyScopedManager


class AgencyUserManager(BaseUserManager, AgencyScopedManager):
    """Combines Django's user manager with agency scoping.
    `create_user` requires an agency context (or explicit agency kwarg) since
    AgencyUser is conceptually scoped, even though it extends AbstractBaseUser directly."""

    use_in_migrations = True

    def _create_user(self, email, password, agency=None, **extra):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email).lower()
        agency = agency or get_current_agency()
        if agency is None:
            raise ValueError("Agency context required to create user")
        user = self.model(email=email, agency=agency, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, agency=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self._create_user(email, password, agency=agency, **extra)
