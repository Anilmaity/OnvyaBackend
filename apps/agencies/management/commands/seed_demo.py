"""Seed a rich demo dataset on top of seed_minimal.

Idempotent: re-running yields no duplicate rows.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.agencies.models import Agency, Depot
from apps.accounts.models import AgencyUser, Role, UserRole
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
    ("olivia.hughes@demo.test", Application.State.IN_PROGRESS),
    ("noah.khan@demo.test", Application.State.PENDING_REVIEW),
    ("driver@demo.test", Application.State.IN_PROGRESS),
]


COURSES = [
    ("Safety Induction", "Mandatory safety orientation", 12, True),
    ("Defensive Driving", "Advanced defensive driving techniques", 24, True),
    ("Manual Handling", "Safe lifting and load handling", 36, True),
    ("Customer Service", "Customer interaction standards", None, False),
    ("First Aid", "Basic first aid certification", 36, False),
]


def _utc(d, t):
    return timezone.make_aware(datetime.combine(d, t), timezone.get_current_timezone())


class Command(BaseCommand):
    help = "Seed full demo data: drivers + shifts + adjustments + documents + training + invoices."

    def handle(self, *args, **opts):
        from django.core.management import call_command
        call_command("seed_minimal")

        agency = Agency.objects.get(slug="demo")
        with agency_context(agency):
            depots = self._seed_depots(agency)
            drivers = self._seed_drivers(agency, depots)
            self._seed_applications(agency)
            self._seed_driver_notes(agency)
            active_drivers = [d for d in drivers if d.status == Driver.Status.ACTIVE]
            self._seed_shifts(agency, active_drivers)
            self._seed_invoicing(agency, active_drivers)
            self._seed_adjustments(agency)
            self._seed_documents(agency, drivers)
            self._seed_training(agency, drivers)

        self.stdout.write(self.style.SUCCESS("seed_demo complete"))

    # --------------------------------------------------------------- depots
    def _seed_depots(self, agency):
        out = {}
        for name in ("London North", "London South"):
            depot, _ = Depot.objects.get_or_create(
                agency=agency, name=name, defaults={"address": f"{name} depot, London"},
            )
            out[name] = depot
        return out

    # --------------------------------------------------------------- drivers
    def _seed_drivers(self, agency, depots):
        from apps.accounts.models import Role, UserRole
        drivers = []
        driver_role = Role.objects.filter(agency=agency, name="Driver").first()
        for first, last, email, status, depot_name, flex in DEMO_DRIVERS:
            # If this driver has a matching AgencyUser, link them and create a login.
            # First active driver (Sarah Chen) gets a known password for mobile testing.
            user = AgencyUser.all_objects.filter(agency=agency, email=email).first()
            if user is None and status == Driver.Status.ACTIVE:
                user = AgencyUser(
                    agency=agency, email=email, first_name=first, last_name=last,
                    is_active=True,
                )
                user.set_password("demo1234")
                user.save()
                if driver_role is not None:
                    UserRole.objects.get_or_create(user=user, role=driver_role)
            driver, _ = Driver.objects.update_or_create(
                agency=agency, email=email,
                defaults={
                    "first_name": first, "last_name": last,
                    "status": status,
                    "depot": depots.get(depot_name),
                    "flex_enrolled": flex,
                    "phone": "+44 20 7000 0000",
                    "joined_at": timezone.now() - timedelta(days=120),
                    "licence_type": "B",
                    "user": user,
                },
            )
            drivers.append(driver)
        return drivers

    def _seed_applications(self, agency):
        for email, state in APPLICATIONS:
            driver = Driver.objects.filter(agency=agency, email=email).first()
            if driver is None:
                continue
            app, _ = Application.objects.get_or_create(
                agency=agency, driver=driver,
                defaults={"state": Application.State.NOT_STARTED},
            )
            app.state = state
            if state == Application.State.PENDING_REVIEW and not app.submitted_at:
                app.submitted_at = timezone.now() - timedelta(days=2)
            app.save()
            kinds_done = {
                Application.State.IN_PROGRESS: [Step.Kind.PERSONAL_DETAILS],
                Application.State.PENDING_REVIEW: [
                    Step.Kind.PERSONAL_DETAILS,
                    Step.Kind.DOCUMENT_UPLOAD,
                    Step.Kind.DVLA_CHECK,
                ],
            }.get(state, [])
            for kind in kinds_done:
                Step.objects.get_or_create(
                    agency=agency, application=app, kind=kind,
                    defaults={
                        "status": Step.Status.PASSED,
                        "started_at": timezone.now() - timedelta(days=3),
                        "completed_at": timezone.now() - timedelta(days=2),
                    },
                )

    def _seed_driver_notes(self, agency):
        admin = AgencyUser.objects.filter(agency=agency, email="admin@demo.test").first()
        target = Driver.objects.filter(agency=agency, email="sarah.chen@demo.test").first()
        if target and not target.notes.exists():
            DriverNote.objects.create(
                agency=agency, driver=target, author=admin,
                body="Completed advanced safety induction.",
            )

    # --------------------------------------------------------------- shifts
    def _seed_shifts(self, agency, drivers):
        from apps.scheduling.models import Shift
        from apps.scheduling.services import ShiftService

        today = timezone.localdate()
        svc = ShiftService()
        for driver_idx, driver in enumerate(drivers):
            for offset in range(-14, 15):
                d = today + timedelta(days=offset)
                if d.weekday() >= 5:
                    continue
                start = _utc(d, time(9, 0))
                end = _utc(d, time(17, 0))
                # Already seeded?
                if Shift.objects.filter(agency=agency, driver=driver, start=start).exists():
                    continue
                if offset < 0:
                    # Past shift: 80% completed, 10% missed, 10% cancelled
                    slot = (driver_idx + abs(offset)) % 10
                    if slot == 8:
                        shift = svc.create(driver=driver, depot=driver.depot, start=start, end=end)
                        svc.mark_missed(shift)
                    elif slot == 9:
                        shift = svc.create(driver=driver, depot=driver.depot, start=start, end=end)
                        svc.cancel(shift)
                    else:
                        shift = svc.create(driver=driver, depot=driver.depot, start=start, end=end)
                        jitter_start = start + timedelta(minutes=(slot * 3) - 7)
                        jitter_end = end + timedelta(minutes=(slot * 5) - 10)
                        svc.complete(shift, actual_start=jitter_start, actual_end=jitter_end)
                else:
                    # Future shift: SCHEDULED
                    svc.create(driver=driver, depot=driver.depot, start=start, end=end)

    def _seed_adjustments(self, agency):
        from apps.scheduling.models import Shift, TimeAdjustment
        from apps.scheduling.services import TimeAdjustmentService
        from apps.invoicing.models import Invoice, InvoiceLineItem

        admin = AgencyUser.objects.filter(agency=agency, email="admin@demo.test").first()
        invoiced_shift_ids = set(
            InvoiceLineItem.objects.exclude(invoice__status=Invoice.Status.VOID)
            .values_list("shift_id", flat=True)
        )
        completed = list(
            Shift.objects.filter(agency=agency, status=Shift.Status.COMPLETED)
            .exclude(id__in=invoiced_shift_ids)
            .order_by("-actual_end")[:8]
        )
        if not completed:
            return
        svc = TimeAdjustmentService()
        plans = [
            ("forgot to clock out", "pending", None),
            ("traffic delay", "pending", None),
            ("extended customer interaction", "pending", None),
            ("clocked in late, made up time later", "approved", "Verified via CCTV."),
            ("personal reasons", "rejected", "Outside policy — please use leave next time."),
        ]
        for shift, (reason, decision, note) in zip(completed, plans):
            if TimeAdjustment.objects.filter(agency=agency, shift=shift).exists():
                continue
            proposed_start = shift.actual_start - timedelta(minutes=15)
            proposed_end = shift.actual_end + timedelta(minutes=15)
            try:
                adj = svc.request(
                    shift=shift, user=admin,
                    proposed_start=proposed_start,
                    proposed_end=proposed_end,
                    reason=reason,
                )
            except Exception:
                continue
            if decision == "approved":
                svc.approve(adj, admin, note or "")
            elif decision == "rejected":
                svc.reject(adj, admin, note or "")

    # --------------------------------------------------------------- documents
    def _seed_documents(self, agency, drivers):
        from apps.documents.models import DriverDocument
        from apps.documents.services import DocumentService

        today = timezone.localdate()
        svc = DocumentService()
        # Per-driver document plans (kind -> expires_on offset days, or None for missing/expired)
        # Tuned so dashboard alerts have content.
        defaults_expiry = {
            DriverDocument.Kind.DRIVING_LICENCE: today + timedelta(days=365),
            DriverDocument.Kind.RIGHT_TO_WORK: today + timedelta(days=730),
            DriverDocument.Kind.INSURANCE: today + timedelta(days=180),
            DriverDocument.Kind.MOT: today + timedelta(days=20),  # EXPIRING
            DriverDocument.Kind.DBS: today + timedelta(days=400),
            DriverDocument.Kind.CPC: today + timedelta(days=15),  # EXPIRING
        }

        for idx, driver in enumerate(drivers):
            for kind, default_exp in defaults_expiry.items():
                expires = default_exp
                # Special cases:
                if idx == 0 and kind == DriverDocument.Kind.DRIVING_LICENCE:
                    expires = today - timedelta(days=5)  # EXPIRED
                if idx == 1 and kind == DriverDocument.Kind.DBS:
                    expires = None  # MISSING
                if DriverDocument.objects.filter(agency=agency, driver=driver, kind=kind).exists():
                    continue
                svc.upsert(
                    driver=driver, kind=kind,
                    reference=f"{kind[:3]}-{driver.id.hex[:6].upper()}",
                    issued_on=(expires - timedelta(days=365)) if expires else None,
                    expires_on=expires,
                )

    # --------------------------------------------------------------- training
    def _seed_training(self, agency, drivers):
        from apps.training.models import Course, Completion
        from apps.training.services import CourseService, CompletionService

        course_svc = CourseService()
        completion_svc = CompletionService()
        courses = {}
        for name, desc, validity, required in COURSES:
            course = course_svc.upsert(
                name=name, description=desc,
                validity_months=validity, is_required=required,
            )
            courses[name] = course

        today = timezone.localdate()
        active_drivers = [d for d in drivers if d.status == Driver.Status.ACTIVE]
        # idx 0, 1 — fully compliant
        # idx 2 — completed all but one EXPIRING (defensive driving completed ~22 months ago)
        # idx 3 — one EXPIRED
        # idx 4 — missing one required
        for idx, driver in enumerate(active_drivers):
            plan = {}
            if idx in (0, 1):
                plan = {n: today - timedelta(days=30) for n in courses}
            elif idx == 2:
                plan = {
                    "Safety Induction": today - timedelta(days=60),
                    "Defensive Driving": today - timedelta(days=22 * 30),  # EXPIRING soon
                    "Manual Handling": today - timedelta(days=300),
                    "Customer Service": today - timedelta(days=400),
                    "First Aid": today - timedelta(days=400),
                }
            elif idx == 3:
                plan = {
                    "Safety Induction": today - timedelta(days=400),  # EXPIRED (>12 months)
                    "Defensive Driving": today - timedelta(days=60),
                    "Manual Handling": today - timedelta(days=60),
                }
            elif idx == 4:
                # missing Manual Handling
                plan = {
                    "Safety Induction": today - timedelta(days=60),
                    "Defensive Driving": today - timedelta(days=60),
                }
            for course_name, completed_on in plan.items():
                course = courses[course_name]
                if Completion.objects.filter(agency=agency, driver=driver, course=course).exists():
                    continue
                completion_svc.upsert(
                    driver=driver, course=course,
                    completed_on=completed_on,
                    certificate_reference=f"CRT-{driver.id.hex[:6].upper()}-{course.id.hex[:4].upper()}",
                )

    # --------------------------------------------------------------- invoicing
    def _seed_invoicing(self, agency, drivers):
        from apps.invoicing.models import Invoice
        from apps.invoicing.services import InvoiceService

        if not drivers:
            return
        svc = InvoiceService()
        today = timezone.localdate()
        period_end = today - timedelta(days=1)
        period_start = period_end - timedelta(days=13)
        # Three drivers, three lifecycle stages
        target_drivers = drivers[:3]
        states = ["paid", "issued", "draft"]
        for driver, state in zip(target_drivers, states):
            if Invoice.objects.filter(
                agency=agency, driver=driver,
                period_start=period_start, period_end=period_end,
            ).exists():
                continue
            invoice = svc.generate_draft(
                driver=driver, period_start=period_start, period_end=period_end,
            )
            if invoice is None:
                continue
            if state == "issued":
                svc.issue(invoice)
            elif state == "paid":
                svc.issue(invoice)
                svc.mark_paid(invoice, paid_on=today - timedelta(days=2))
