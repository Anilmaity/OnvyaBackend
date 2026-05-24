import random

from django.db import transaction

from apps.common.context import get_current_agency
from apps.common.services import AgencyScopedService
from apps.drivers.models import Driver, DriverNote


class DriverService(AgencyScopedService):
    model = Driver

    def create(self, *, first_name, last_name, email, phone="", ni_number="", date_of_birth=None,
               licence_type="", depot=None, flex_enrolled=False):
        agency = get_current_agency()
        email = email.lower().strip()
        with transaction.atomic():
            driver = Driver(
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                ni_number=ni_number,
                date_of_birth=date_of_birth,
                licence_type=licence_type or "",
                depot=depot,
                flex_enrolled=flex_enrolled,
                status=Driver.Status.PENDING,
                registration_code=self._generate_code(),
            )
            driver.user = self._ensure_login(agency, email, first_name, last_name)
            self.save(driver)
        from apps.drivers.tasks import send_driver_registration_email
        send_driver_registration_email.delay(str(driver.id))
        return driver

    def _generate_code(self):
        for _ in range(10):
            code = f"{random.randint(0, 999999):06d}"
            if not Driver.objects.filter(registration_code=code).exists():
                return code
        return f"{random.randint(0, 999999):06d}"

    def _ensure_login(self, agency, email, first_name, last_name):
        from apps.accounts.models import AgencyUser, Role, UserRole
        user = AgencyUser.all_objects.filter(agency=agency, email=email).first()
        if user is None:
            user = AgencyUser(
                agency=agency, email=email,
                first_name=first_name, last_name=last_name,
                is_active=False,
            )
            user.set_unusable_password()
            user.save()
        driver_role = Role.objects.filter(agency=agency, name="Driver").first()
        if driver_role is not None:
            UserRole.objects.get_or_create(user=user, role=driver_role)
        return user

    def update(self, driver, **fields):
        for k, v in fields.items():
            setattr(driver, k, v)
        return self.save(driver)

    def suspend(self, driver, reason):
        if driver.status == Driver.Status.SUSPENDED:
            raise ValueError("Driver already suspended")
        if driver.status == Driver.Status.OFFBOARDED:
            raise ValueError("Cannot suspend an offboarded driver")
        driver.status = Driver.Status.SUSPENDED
        driver.suspension_reason = reason
        return self.save(driver)

    def reactivate(self, driver):
        if driver.status != Driver.Status.SUSPENDED:
            raise ValueError("Only suspended drivers can be reactivated")
        driver.status = Driver.Status.ACTIVE
        driver.suspension_reason = ""
        return self.save(driver)

    def offboard(self, driver, reason):
        if driver.status == Driver.Status.OFFBOARDED:
            raise ValueError("Driver already offboarded")
        driver.status = Driver.Status.OFFBOARDED
        driver.offboard_reason = reason
        return self.save(driver)


class DriverNoteService(AgencyScopedService):
    model = DriverNote

    def add(self, *, driver, author, body):
        note = DriverNote(driver=driver, author=author, body=body)
        return self.save(note)
