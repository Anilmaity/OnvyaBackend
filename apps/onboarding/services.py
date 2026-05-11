from django.utils import timezone

from apps.accounts.models import AgencyUser, Role, UserRole
from apps.common.services import AgencyScopedService
from apps.drivers.models import Driver
from apps.drivers.services import DriverNoteService
from apps.onboarding.models import Application, Step, ApplicationDocument


STEP_ORDER = [
    Step.Kind.PERSONAL_DETAILS,
    Step.Kind.DOCUMENT_UPLOAD,
    Step.Kind.OCR,
    Step.Kind.DVLA_CHECK,
    Step.Kind.RTW_CHECK,
    Step.Kind.CONTRACT_SIGNATURE,
]


class IllegalTransition(ValueError):
    pass


class ApplicationService(AgencyScopedService):
    model = Application

    def start(self, driver):
        existing = Application.objects.filter(driver=driver).first()
        if existing and existing.state not in (Application.State.REJECTED,):
            raise IllegalTransition("Driver already has an active application")
        app = Application(driver=driver, state=Application.State.IN_PROGRESS)
        self.save(app)
        step_service = StepService()
        for kind in STEP_ORDER:
            step = Step(application=app, kind=kind, status=Step.Status.PENDING)
            step_service.save(step)
        # Trigger stub checks (eager Celery → inline)
        from apps.onboarding.tasks import run_dvla_check, run_rtw_check
        run_dvla_check.delay(str(app.id))
        run_rtw_check.delay(str(app.id))
        # Mark personal-details + contract-signature pass automatically for this slice
        for kind in (Step.Kind.PERSONAL_DETAILS, Step.Kind.CONTRACT_SIGNATURE):
            step = Step.objects.get(application=app, kind=kind)
            step.status = Step.Status.PASSED
            step.completed_at = timezone.now()
            step.outcome = {"auto": True}
            step_service.save(step)
        return app

    def upload_document(self, application, kind, uploaded_file):
        if application.state != Application.State.IN_PROGRESS:
            raise IllegalTransition("Documents can only be uploaded while application is in progress")
        doc = ApplicationDocument(application=application, kind=kind, file=uploaded_file)
        DocumentService().save(doc)
        # Mark the DOCUMENT_UPLOAD step passed (any successful upload satisfies it for this slice)
        step = Step.objects.get(application=application, kind=Step.Kind.DOCUMENT_UPLOAD)
        step.status = Step.Status.PASSED
        step.completed_at = timezone.now()
        StepService().save(step)
        from apps.onboarding.tasks import run_ocr
        run_ocr.delay(str(doc.id))
        return doc

    def submit_for_review(self, application):
        if application.state != Application.State.IN_PROGRESS:
            raise IllegalTransition(f"Cannot submit from state {application.state}")
        not_passed = application.steps.exclude(status=Step.Status.PASSED).exists()
        if not_passed:
            raise IllegalTransition("All steps must be PASSED before submitting")
        application.state = Application.State.PENDING_REVIEW
        application.submitted_at = timezone.now()
        return self.save(application)

    def approve(self, application, by_user):
        if application.state != Application.State.PENDING_REVIEW:
            raise IllegalTransition(f"Cannot approve from state {application.state}")
        application.state = Application.State.APPROVED
        application.decided_at = timezone.now()
        application.decided_by = by_user
        self.save(application)
        # Promote driver
        driver = application.driver
        driver.status = Driver.Status.ACTIVE
        driver.joined_at = timezone.now()
        # Create user for driver if missing, assign Driver role
        if driver.user is None:
            driver_user = AgencyUser(
                agency=driver.agency, email=driver.email,
                first_name=driver.first_name, last_name=driver.last_name,
            )
            driver_user.set_unusable_password()
            driver_user.save()
            driver.user = driver_user
            role = Role.objects.filter(name="Driver").first()
            if role:
                UserRole.objects.create(user=driver_user, role=role)
        driver.save()
        return application

    def reject(self, application, by_user, reason):
        if application.state != Application.State.PENDING_REVIEW:
            raise IllegalTransition(f"Cannot reject from state {application.state}")
        application.state = Application.State.REJECTED
        application.decided_at = timezone.now()
        application.decided_by = by_user
        application.rejection_reason = reason
        self.save(application)
        application.driver.status = Driver.Status.OFFBOARDED
        application.driver.offboard_reason = f"application_rejected: {reason}"
        application.driver.save()
        return application

    def request_more_info(self, application, by_user, message):
        if application.state != Application.State.PENDING_REVIEW:
            raise IllegalTransition(f"Cannot request more info from state {application.state}")
        application.state = Application.State.IN_PROGRESS
        application.submitted_at = None
        self.save(application)
        DriverNoteService().add(driver=application.driver, author=by_user, body=f"More info requested: {message}")
        return application


class StepService(AgencyScopedService):
    model = Step


class DocumentService(AgencyScopedService):
    model = ApplicationDocument
