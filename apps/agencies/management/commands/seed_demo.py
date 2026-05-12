from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.agencies.models import Agency, Depot
from apps.accounts.models import AgencyUser, Role, Permission, RolePermission, UserRole
from apps.accounts.data.permission_catalogue import PERMISSIONS, ROLE_MATRIX
from apps.drivers.models import Driver, DriverNote
from apps.onboarding.models import Application, Step
from apps.common.context import agency_context


DEMO_DRIVERS = [
    ("James", "Wilson", "james.wilson@demo.test", Driver.Status.ACTIVE, "London North", True),
    ("Sarah", "Chen", "sarah.chen@demo.test", Driver.Status.ACTIVE, "London North", True),
    ("Marcus", "Reid", "marcus.reid@demo.test", Driver.Status.ACTIVE, "London South", False),
    ("Aisha", "Patel", "aisha.patel@demo.test", Driver.Status.ACTIVE, "London South", True),
    ("David", "Kowalski", "david.kowalski@demo.test", Driver.Status.RESTING, "London North", False),
    ("Emily", "Tran", "emily.tran@demo.test", Driver.Status.SUSPENDED, "London North", False),
    ("Liam", "Murphy", "liam.murphy@demo.test", Driver.Status.OFFBOARDED, "London South", False),
    ("Olivia", "Hughes", "olivia.hughes@demo.test", Driver.Status.PENDING, "London North", False),
    ("Noah", "Khan", "noah.khan@demo.test", Driver.Status.PENDING, "London South", False),
    ("Sophia", "Garcia", "sophia.garcia@demo.test", Driver.Status.ACTIVE, "London North", False),
]


APPLICATIONS = [
    # email, state
    ("olivia.hughes@demo.test", Application.State.IN_PROGRESS),
    ("noah.khan@demo.test", Application.State.PENDING_REVIEW),
    ("driver@demo.test", Application.State.IN_PROGRESS),
]


class Command(BaseCommand):
    help = "Seed richer demo data on top of seed_minimal."

    def handle(self, *args, **opts):
        from django.core.management import call_command
        call_command("seed_minimal")

        agency = Agency.objects.get(slug="demo")
        with agency_context(agency):
            depots = {}
            for name in {"London North", "London South"}:
                depot, _ = Depot.objects.get_or_create(
                    agency=agency, name=name, defaults={"address": f"{name} depot, London"}
                )
                depots[name] = depot

            for first, last, email, status, depot_name, flex in DEMO_DRIVERS:
                Driver.objects.update_or_create(
                    agency=agency,
                    email=email,
                    defaults={
                        "first_name": first,
                        "last_name": last,
                        "status": status,
                        "depot": depots.get(depot_name),
                        "flex_enrolled": flex,
                        "phone": "+44 20 7000 0000",
                        "joined_at": timezone.now() - timedelta(days=120),
                        "licence_type": "B",
                    },
                )

            admin = AgencyUser.objects.filter(agency=agency, email="admin@demo.test").first()

            for email, target_state in APPLICATIONS:
                driver = Driver.objects.filter(agency=agency, email=email).first()
                if driver is None:
                    continue
                app, _ = Application.objects.get_or_create(
                    agency=agency, driver=driver, defaults={"state": Application.State.NOT_STARTED}
                )
                app.state = target_state
                if target_state == Application.State.PENDING_REVIEW and not app.submitted_at:
                    app.submitted_at = timezone.now() - timedelta(days=2)
                app.save()

                # Seed steps if missing
                kinds_done = {
                    Application.State.IN_PROGRESS: [Step.Kind.PERSONAL_DETAILS],
                    Application.State.PENDING_REVIEW: [
                        Step.Kind.PERSONAL_DETAILS,
                        Step.Kind.DOCUMENT_UPLOAD,
                        Step.Kind.DVLA_CHECK,
                    ],
                }.get(target_state, [])
                for kind in kinds_done:
                    Step.objects.get_or_create(
                        agency=agency,
                        application=app,
                        kind=kind,
                        defaults={
                            "status": Step.Status.PASSED,
                            "started_at": timezone.now() - timedelta(days=3),
                            "completed_at": timezone.now() - timedelta(days=2),
                        },
                    )

            # A couple of driver notes
            target = Driver.objects.filter(agency=agency, email="sarah.chen@demo.test").first()
            if target and not target.notes.exists():
                DriverNote.objects.create(
                    agency=agency, driver=target, author=admin,
                    body="Completed advanced safety induction.",
                )

        self.stdout.write(self.style.SUCCESS("seed_demo complete"))
