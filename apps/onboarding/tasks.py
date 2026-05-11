from celery import shared_task
from django.utils import timezone

from apps.common.context import agency_context
from apps.onboarding.adapters.dvla import DvlaAdapter
from apps.onboarding.adapters.rtw import RtwAdapter
from apps.onboarding.adapters.ocr import OcrAdapter
from apps.onboarding.models import Application, Step, ApplicationDocument


def _complete_step(application, kind, outcome, status=Step.Status.PASSED):
    step = Step.all_objects.filter(application=application, kind=kind).first()
    if step is None:
        return
    step.status = status
    step.outcome = outcome
    step.started_at = step.started_at or timezone.now()
    step.completed_at = timezone.now()
    step.save()


@shared_task
def run_dvla_check(application_id):
    app = Application.all_objects.get(id=application_id)
    with agency_context(app.agency):
        outcome = DvlaAdapter().check(app.driver)
        _complete_step(app, Step.Kind.DVLA_CHECK, outcome)


@shared_task
def run_rtw_check(application_id):
    app = Application.all_objects.get(id=application_id)
    with agency_context(app.agency):
        outcome = RtwAdapter().check(app.driver)
        _complete_step(app, Step.Kind.RTW_CHECK, outcome)


@shared_task
def run_ocr(application_document_id):
    doc = ApplicationDocument.all_objects.get(id=application_document_id)
    app = doc.application
    with agency_context(app.agency):
        payload = OcrAdapter().extract(doc.file.path if doc.file else "", doc.kind)
        doc.ocr_payload = payload
        doc.save()
        _complete_step(app, Step.Kind.OCR, payload)
