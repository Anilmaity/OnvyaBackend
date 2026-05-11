from apps.common.services import AgencyScopedService
from apps.drivers.models import Driver, DriverNote


class DriverService(AgencyScopedService):
    model = Driver

    def create(self, *, first_name, last_name, email, phone="", ni_number="", date_of_birth=None,
               licence_type="", depot=None, flex_enrolled=False):
        driver = Driver(
            first_name=first_name,
            last_name=last_name,
            email=email.lower().strip(),
            phone=phone,
            ni_number=ni_number,
            date_of_birth=date_of_birth,
            licence_type=licence_type or "",
            depot=depot,
            flex_enrolled=flex_enrolled,
            status=Driver.Status.PENDING,
        )
        return self.save(driver)

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
