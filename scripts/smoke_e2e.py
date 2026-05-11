"""End-to-end smoke: walk the seeded application from start to APPROVED."""
import os, sys, django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from graphene.test import Client
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.agencies.models import Agency
from apps.accounts.models import AgencyUser
from apps.drivers.models import Driver
from apps.onboarding.models import Application
from apps.common.context import set_current_agency, clear_current_agency
from config.schema import schema


class Req:
    pass


def main():
    agency = Agency.objects.get(slug="demo")
    set_current_agency(agency)
    try:
        admin = AgencyUser.objects.get(agency=agency, email="admin@demo.test")
        driver = Driver.objects.get(email="driver@demo.test")
        application = Application.objects.filter(driver=driver).first()
        if application is None:
            print("No seeded application; aborting.")
            return

        req = Req()
        req.user = admin
        req.current_agency = agency

        from apps.onboarding.services import ApplicationService
        # Upload one document per step type to pass all steps
        svc = ApplicationService()
        for step in application.steps.all():
            f = SimpleUploadedFile(f"{step.kind.lower()}.pdf", b"smoke-bytes", content_type="application/pdf")
            svc.upload_document(application, step.kind, f)

        c = Client(schema)
        r = c.execute(
            f'mutation {{ submitApplicationForReview(applicationId: "{application.id}") {{ __typename }} }}',
            context=req,
        )
        print("submit:", r)
        r = c.execute(
            f'mutation {{ approveApplication(applicationId: "{application.id}") {{ __typename }} }}',
            context=req,
        )
        print("approve:", r)

        application.refresh_from_db()
        driver.refresh_from_db()
        print(f"Final: app.state={application.state}, driver.status={driver.status}, driver.joined_at={driver.joined_at}")
    finally:
        clear_current_agency()


if __name__ == "__main__":
    main()
