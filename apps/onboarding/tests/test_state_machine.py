import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.agencies.models import Agency
from apps.accounts.factories import AgencyUserFactory
from apps.accounts.models import Role
from apps.drivers.factories import DriverFactory
from apps.drivers.models import Driver
from apps.onboarding.models import Application, Step
from apps.onboarding.services import ApplicationService, IllegalTransition
from apps.common.context import set_current_agency, clear_current_agency


@pytest.fixture
def ctx(db):
    agency = Agency.objects.create(name="A", slug="a")
    set_current_agency(agency)
    Role.objects.create(agency=agency, name="Driver", is_system=True)
    op = AgencyUserFactory(agency=agency, email="op@a.test", password="x")
    yield agency, op
    clear_current_agency()


def test_start_creates_application_and_steps(ctx):
    agency, _ = ctx
    driver = DriverFactory(agency=agency)
    app = ApplicationService().start(driver)
    assert app.state == Application.State.IN_PROGRESS
    assert app.steps.count() == 6
    assert app.steps.get(kind=Step.Kind.DVLA_CHECK).status == Step.Status.PASSED
    assert app.steps.get(kind=Step.Kind.RTW_CHECK).status == Step.Status.PASSED


def test_start_rejected_when_active_application_exists(ctx):
    agency, _ = ctx
    driver = DriverFactory(agency=agency)
    ApplicationService().start(driver)
    with pytest.raises(IllegalTransition):
        ApplicationService().start(driver)


def test_upload_document_passes_steps(ctx):
    agency, _ = ctx
    driver = DriverFactory(agency=agency)
    app = ApplicationService().start(driver)
    f = SimpleUploadedFile("licence.pdf", b"fakebytes", content_type="application/pdf")
    doc = ApplicationService().upload_document(app, "LICENCE", f)
    doc.refresh_from_db()
    assert doc.ocr_payload
    assert app.steps.get(kind=Step.Kind.DOCUMENT_UPLOAD).status == Step.Status.PASSED
    assert app.steps.get(kind=Step.Kind.OCR).status == Step.Status.PASSED


def test_submit_requires_all_steps_passed(ctx):
    agency, _ = ctx
    driver = DriverFactory(agency=agency)
    app = ApplicationService().start(driver)
    with pytest.raises(IllegalTransition):
        ApplicationService().submit_for_review(app)


def test_submit_then_approve(ctx):
    agency, op = ctx
    driver = DriverFactory(agency=agency)
    app = ApplicationService().start(driver)
    f = SimpleUploadedFile("licence.pdf", b"x", content_type="application/pdf")
    ApplicationService().upload_document(app, "LICENCE", f)
    ApplicationService().submit_for_review(app)
    app.refresh_from_db()
    assert app.state == Application.State.PENDING_REVIEW

    ApplicationService().approve(app, op)
    app.refresh_from_db()
    driver.refresh_from_db()
    assert app.state == Application.State.APPROVED
    assert driver.status == Driver.Status.ACTIVE
    assert driver.joined_at is not None
    assert driver.user is not None


def test_reject_offboards_driver(ctx):
    agency, op = ctx
    driver = DriverFactory(agency=agency)
    app = ApplicationService().start(driver)
    f = SimpleUploadedFile("licence.pdf", b"x", content_type="application/pdf")
    ApplicationService().upload_document(app, "LICENCE", f)
    ApplicationService().submit_for_review(app)
    ApplicationService().reject(app, op, "incomplete documents")
    app.refresh_from_db(); driver.refresh_from_db()
    assert app.state == Application.State.REJECTED
    assert app.rejection_reason == "incomplete documents"
    assert driver.status == Driver.Status.OFFBOARDED


def test_request_more_info(ctx):
    agency, op = ctx
    driver = DriverFactory(agency=agency)
    app = ApplicationService().start(driver)
    f = SimpleUploadedFile("licence.pdf", b"x", content_type="application/pdf")
    ApplicationService().upload_document(app, "LICENCE", f)
    ApplicationService().submit_for_review(app)
    ApplicationService().request_more_info(app, op, "passport please")
    app.refresh_from_db()
    assert app.state == Application.State.IN_PROGRESS
    assert app.driver.notes.count() == 1
