from django.core.management.base import BaseCommand

from apps.agencies.models import Agency
from apps.accounts.models import AgencyUser
from apps.common.context import agency_context
from apps.drivers.models import Driver
from apps.onboarding.models import Application


class Command(BaseCommand):
    help = "Ensure a driver user has a linked Driver profile and a clean (no) application."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="driver@demo.test")
        parser.add_argument("--agency", default="demo")

    def handle(self, *args, **opts):
        agency = Agency.objects.get(slug=opts["agency"])
        with agency_context(agency):
            user = AgencyUser.all_objects.filter(agency=agency, email=opts["email"]).first()
            if user is None:
                self.stderr.write(f"No user {opts['email']} in agency {agency.slug}")
                return
            driver = Driver.objects.filter(agency=agency, user=user).first()
            if driver is None:
                driver = Driver.objects.filter(agency=agency, email=opts["email"]).first()
                if driver is None:
                    driver = Driver(agency=agency, email=opts["email"],
                                    first_name=user.first_name or "Test",
                                    last_name=user.last_name or "Driver",
                                    status=Driver.Status.PENDING)
                driver.user = user
                driver.save()
            Application.objects.filter(driver=driver).delete()
            self.stdout.write(self.style.SUCCESS(
                f"Driver {driver.id} linked to {user.email}; application cleared."))
