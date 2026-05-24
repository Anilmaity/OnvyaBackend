import graphene
from graphene_django import DjangoObjectType
from graphene_file_upload.scalars import Upload
from django.utils import timezone

from apps.common.graphql_types import MutationResult, Success, ValidationError, FieldError, PermissionDenied
from apps.common.permissions import permission_required
from apps.drivers.models import Driver
from apps.onboarding.models import Application, Step, ApplicationDocument
from apps.onboarding.services import ApplicationService, IllegalTransition, StepService
from apps.onboarding.selectors import list_applications


class StepType(DjangoObjectType):
    class Meta:
        model = Step
        fields = ("id", "kind", "status", "outcome", "started_at", "completed_at", "application")


class ApplicationDocumentType(DjangoObjectType):
    class Meta:
        model = ApplicationDocument
        fields = ("id", "kind", "file", "ocr_payload", "uploaded_at", "application")


class ApplicationType(DjangoObjectType):
    steps = graphene.List(graphene.NonNull(StepType), required=True)
    documents = graphene.List(graphene.NonNull(ApplicationDocumentType), required=True)

    class Meta:
        model = Application
        fields = ("id", "driver", "state", "submitted_at", "decided_at",
                  "decided_by", "rejection_reason", "created_at", "updated_at")

    def resolve_steps(self, info):
        return list(self.steps.all().order_by("created_at"))

    def resolve_documents(self, info):
        return list(self.documents.all().order_by("-uploaded_at"))


class ApplicationFilter(graphene.InputObjectType):
    state = graphene.String()
    search = graphene.String()


def _validation(field, message):
    return ValidationError(field_errors=[FieldError(field=field, message=message)])


def _self_driver(info):
    """Return the authenticated user's own Driver, or None."""
    user = getattr(info.context, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return None
    return getattr(user, "driver_profile", None)


class StartApplication(graphene.Mutation):
    class Arguments:
        driver_id = graphene.ID(required=True)

    Output = MutationResult

    @permission_required("applications.create")
    def mutate(self, info, driver_id):
        driver = Driver.objects.filter(id=driver_id).first()
        if driver is None:
            return _validation("driver_id", "Driver not found")
        try:
            app = ApplicationService().start(driver)
        except IllegalTransition as e:
            return _validation("state", str(e))
        return Success(id=str(app.id), message="started")


class UploadApplicationDocument(graphene.Mutation):
    class Arguments:
        application_id = graphene.ID(required=True)
        kind = graphene.String(required=True)
        file = Upload(required=True)

    Output = MutationResult

    @permission_required("applications.update")
    def mutate(self, info, application_id, kind, file):
        app = Application.objects.filter(id=application_id).first()
        if app is None:
            return _validation("application_id", "Application not found")
        try:
            doc = ApplicationService().upload_document(app, kind, file)
        except IllegalTransition as e:
            return _validation("state", str(e))
        return Success(id=str(doc.id), message="uploaded")


class SubmitApplicationForReview(graphene.Mutation):
    class Arguments:
        application_id = graphene.ID(required=True)

    Output = MutationResult

    @permission_required("applications.update")
    def mutate(self, info, application_id):
        app = Application.objects.filter(id=application_id).first()
        if app is None:
            return _validation("application_id", "Application not found")
        try:
            ApplicationService().submit_for_review(app)
        except IllegalTransition as e:
            return _validation("state", str(e))
        return Success(id=str(app.id), message="submitted")


class ApproveApplication(graphene.Mutation):
    class Arguments:
        application_id = graphene.ID(required=True)

    Output = MutationResult

    @permission_required("applications.approve")
    def mutate(self, info, application_id):
        app = Application.objects.filter(id=application_id).first()
        if app is None:
            return _validation("application_id", "Application not found")
        try:
            ApplicationService().approve(app, info.context.user)
        except IllegalTransition as e:
            return _validation("state", str(e))
        return Success(id=str(app.id), message="approved")


class RejectApplication(graphene.Mutation):
    class Arguments:
        application_id = graphene.ID(required=True)
        reason = graphene.String(required=True)

    Output = MutationResult

    @permission_required("applications.approve")
    def mutate(self, info, application_id, reason):
        app = Application.objects.filter(id=application_id).first()
        if app is None:
            return _validation("application_id", "Application not found")
        try:
            ApplicationService().reject(app, info.context.user, reason)
        except IllegalTransition as e:
            return _validation("state", str(e))
        return Success(id=str(app.id), message="rejected")


class RequestMoreInfo(graphene.Mutation):
    class Arguments:
        application_id = graphene.ID(required=True)
        message = graphene.String(required=True)

    Output = MutationResult

    @permission_required("applications.approve")
    def mutate(self, info, application_id, message):
        app = Application.objects.filter(id=application_id).first()
        if app is None:
            return _validation("application_id", "Application not found")
        try:
            ApplicationService().request_more_info(app, info.context.user, message)
        except IllegalTransition as e:
            return _validation("state", str(e))
        return Success(id=str(app.id), message="info_requested")


class StartMyApplication(graphene.Mutation):
    Output = MutationResult

    def mutate(self, info):
        driver = _self_driver(info)
        if driver is None:
            return PermissionDenied(code="no_driver", message="No driver profile for current user")
        existing = Application.objects.filter(driver=driver).first()
        if existing and existing.state != Application.State.REJECTED:
            return Success(id=str(existing.id), message="already_started")
        try:
            app = ApplicationService().start(driver)
        except IllegalTransition as e:
            return _validation("state", str(e))
        return Success(id=str(app.id), message="started")


class SaveMyPersonalDetails(graphene.Mutation):
    class Arguments:
        first_name = graphene.String(required=True)
        last_name = graphene.String(required=True)
        phone = graphene.String()
        date_of_birth = graphene.Date()

    Output = MutationResult

    def mutate(self, info, first_name, last_name, phone=None, date_of_birth=None):
        driver = _self_driver(info)
        if driver is None:
            return PermissionDenied(code="no_driver", message="No driver profile for current user")
        app = Application.objects.filter(driver=driver).first()
        if app is None:
            return _validation("application", "No application; start onboarding first")
        driver.first_name = first_name
        driver.last_name = last_name
        if phone is not None:
            driver.phone = phone
        if date_of_birth is not None:
            driver.date_of_birth = date_of_birth
        driver.save()
        step = Step.objects.filter(application=app, kind=Step.Kind.PERSONAL_DETAILS).first()
        if step is not None:
            step.outcome = {
                **(step.outcome or {}),
                "first_name": first_name, "last_name": last_name,
                "phone": phone or "", "date_of_birth": str(date_of_birth) if date_of_birth else None,
            }
            step.status = Step.Status.PASSED
            step.completed_at = timezone.now()
            StepService().save(step)
        return Success(id=str(driver.id), message="personal_details_saved")


class SaveMyVehicle(graphene.Mutation):
    class Arguments:
        registration = graphene.String(required=True)
        make = graphene.String(required=True)
        model = graphene.String(required=True)
        year = graphene.Int()
        colour = graphene.String()

    Output = MutationResult

    def mutate(self, info, registration, make, model, year=None, colour=None):
        driver = _self_driver(info)
        if driver is None:
            return PermissionDenied(code="no_driver", message="No driver profile for current user")
        from apps.vehicles.models import Vehicle
        from apps.vehicles.services import VehicleService
        v = Vehicle.objects.filter(driver=driver).first() or Vehicle(driver=driver)
        v.registration = registration
        v.make = make
        v.model = model
        v.year = year
        v.colour = colour or ""
        VehicleService().save(v)
        return Success(id=str(v.id), message="vehicle_saved")


class SaveMyBackgroundCheck(graphene.Mutation):
    class Arguments:
        ni_number = graphene.String(required=True)
        dbs_consent = graphene.Boolean(required=True)

    Output = MutationResult

    def mutate(self, info, ni_number, dbs_consent):
        driver = _self_driver(info)
        if driver is None:
            return PermissionDenied(code="no_driver", message="No driver profile for current user")
        if not dbs_consent:
            return _validation("dbs_consent", "DBS consent is required to proceed")
        driver.ni_number = ni_number
        driver.dbs_consent = True
        driver.dbs_consent_at = timezone.now()
        driver.save()
        return Success(id=str(driver.id), message="background_saved")


class Query(graphene.ObjectType):
    applications = graphene.List(graphene.NonNull(ApplicationType), filter=ApplicationFilter(), required=True)
    application = graphene.Field(ApplicationType, id=graphene.ID(required=True))
    my_application = graphene.Field(ApplicationType)

    @permission_required("applications.read")
    def resolve_applications(self, info, filter=None):
        state = filter.get("state") if filter else None
        search = filter.get("search") if filter else None
        return list(list_applications(state=state, search=search))

    @permission_required("applications.read")
    def resolve_application(self, info, id):
        return Application.objects.filter(id=id).first()

    def resolve_my_application(self, info):
        user = getattr(info.context, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return None
        driver = getattr(user, "driver_profile", None)
        if driver is None:
            return None
        return Application.objects.filter(driver=driver).first()


class Mutation(graphene.ObjectType):
    start_application = StartApplication.Field()
    upload_application_document = UploadApplicationDocument.Field()
    submit_application_for_review = SubmitApplicationForReview.Field()
    approve_application = ApproveApplication.Field()
    reject_application = RejectApplication.Field()
    request_more_info = RequestMoreInfo.Field()
    start_my_application = StartMyApplication.Field()
    save_my_personal_details = SaveMyPersonalDetails.Field()
    save_my_vehicle = SaveMyVehicle.Field()
    save_my_background_check = SaveMyBackgroundCheck.Field()
