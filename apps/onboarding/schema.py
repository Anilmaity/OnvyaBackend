import graphene
from graphene_django import DjangoObjectType
from graphene_file_upload.scalars import Upload

from apps.common.graphql_types import MutationResult, Success, ValidationError, FieldError
from apps.common.permissions import permission_required
from apps.drivers.models import Driver
from apps.onboarding.models import Application, Step, ApplicationDocument
from apps.onboarding.services import ApplicationService, IllegalTransition
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


class Query(graphene.ObjectType):
    applications = graphene.List(graphene.NonNull(ApplicationType), filter=ApplicationFilter(), required=True)
    application = graphene.Field(ApplicationType, id=graphene.ID(required=True))
    my_application = graphene.Field(ApplicationType)

    @permission_required("applications.read")
    def resolve_applications(self, info, filter=None):
        f = filter or ApplicationFilter()
        return list(list_applications(state=f.state, search=f.search))

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
