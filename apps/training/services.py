from datetime import timedelta

from dateutil.relativedelta import relativedelta
from django.utils import timezone

from apps.common.services import AgencyScopedService
from apps.training.models import Course, Completion


EXPIRING_WINDOW_DAYS = 30


def compute_status(expires_on):
    if expires_on is None:
        return Completion.Status.VALID
    today = timezone.localdate()
    if expires_on < today:
        return Completion.Status.EXPIRED
    if expires_on <= today + timedelta(days=EXPIRING_WINDOW_DAYS):
        return Completion.Status.EXPIRING
    return Completion.Status.VALID


def compute_expires_on(completed_on, validity_months):
    if validity_months is None:
        return None
    return completed_on + relativedelta(months=int(validity_months))


class CourseService(AgencyScopedService):
    model = Course

    def upsert(self, *, name, description="", validity_months=None, is_required=False):
        course = Course.objects.filter(name=name).first()
        if course is None:
            course = Course(name=name)
        course.description = description or ""
        course.validity_months = validity_months
        course.is_required = bool(is_required)
        return self.save(course)


class CompletionService(AgencyScopedService):
    model = Completion

    def upsert(self, *, driver, course, completed_on, certificate_reference="", notes=""):
        comp = Completion.objects.filter(driver=driver, course=course).first()
        if comp is None:
            comp = Completion(driver=driver, course=course)
        comp.completed_on = completed_on
        comp.expires_on = compute_expires_on(completed_on, course.validity_months)
        comp.status = compute_status(comp.expires_on)
        comp.certificate_reference = certificate_reference or ""
        comp.notes = notes or ""
        return self.save(comp)

    @classmethod
    def recompute_all(cls, agency=None):
        qs = Completion.objects.all()
        if agency is not None:
            qs = qs.filter(agency=agency)
        changed = 0
        for comp in qs:
            new = compute_status(comp.expires_on)
            if new != comp.status:
                comp.status = new
                comp.save(update_fields=["status", "updated_at"])
                changed += 1
        return changed


def missing_required_courses(driver):
    return Course.objects.filter(
        agency=driver.agency, is_required=True
    ).exclude(completions__driver=driver)
