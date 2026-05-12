import graphene
from graphene_django import DjangoObjectType

from apps.common.graphql_types import MutationResult, Success, ValidationError, FieldError
from apps.common.permissions import permission_required
from apps.drivers.models import Driver
from apps.training.models import Course, Completion
from apps.training.services import CourseService, CompletionService, missing_required_courses
from apps.training.selectors import list_courses, list_completions


def _validation(field, message):
    return ValidationError(field_errors=[FieldError(field=field, message=message)])


class CourseType(DjangoObjectType):
    class Meta:
        model = Course
        fields = ("id", "name", "description", "validity_months", "is_required",
                  "created_at", "updated_at")


class CompletionType(DjangoObjectType):
    class Meta:
        model = Completion
        fields = ("id", "driver", "course", "completed_on", "expires_on", "status",
                  "certificate_reference", "notes", "created_at", "updated_at")


class CompletionFilter(graphene.InputObjectType):
    driver_id = graphene.ID()
    course_id = graphene.ID()
    status = graphene.String()


class DriverTrainingType(graphene.ObjectType):
    completed = graphene.List(graphene.NonNull(CompletionType), required=True)
    missing = graphene.List(graphene.NonNull(CourseType), required=True)


class UpsertCourseInput(graphene.InputObjectType):
    name = graphene.String(required=True)
    description = graphene.String()
    validity_months = graphene.Int()
    is_required = graphene.Boolean()


class UpsertCourse(graphene.Mutation):
    class Arguments:
        input = UpsertCourseInput(required=True)
    Output = MutationResult

    @permission_required("training.write")
    def mutate(self, info, input):
        course = CourseService().upsert(
            name=input.name,
            description=input.description or "",
            validity_months=input.validity_months,
            is_required=bool(input.is_required),
        )
        return Success(id=str(course.id), message="upserted")


class DeleteCourse(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
    Output = MutationResult

    @permission_required("training.write")
    def mutate(self, info, id):
        course = Course.objects.filter(id=id).first()
        if course is None:
            return _validation("id", "Course not found")
        course.delete()
        return Success(id=str(id), message="deleted")


class RecordCompletionInput(graphene.InputObjectType):
    driver_id = graphene.ID(required=True)
    course_id = graphene.ID(required=True)
    completed_on = graphene.Date(required=True)
    certificate_reference = graphene.String()
    notes = graphene.String()


class RecordCompletion(graphene.Mutation):
    class Arguments:
        input = RecordCompletionInput(required=True)
    Output = MutationResult

    @permission_required("training.write")
    def mutate(self, info, input):
        driver = Driver.objects.filter(id=input.driver_id).first()
        if driver is None:
            return _validation("driver_id", "Driver not found")
        course = Course.objects.filter(id=input.course_id).first()
        if course is None:
            return _validation("course_id", "Course not found")
        comp = CompletionService().upsert(
            driver=driver, course=course,
            completed_on=input.completed_on,
            certificate_reference=input.certificate_reference or "",
            notes=input.notes or "",
        )
        return Success(id=str(comp.id), message="recorded")


class DeleteCompletion(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
    Output = MutationResult

    @permission_required("training.write")
    def mutate(self, info, id):
        comp = Completion.objects.filter(id=id).first()
        if comp is None:
            return _validation("id", "Completion not found")
        comp.delete()
        return Success(id=str(id), message="deleted")


class Query(graphene.ObjectType):
    courses = graphene.List(graphene.NonNull(CourseType), required=True)
    completions = graphene.List(
        graphene.NonNull(CompletionType), filter=CompletionFilter(), required=True,
    )
    driver_training = graphene.Field(DriverTrainingType, driver_id=graphene.ID(required=True))

    @permission_required("training.read")
    def resolve_courses(self, info):
        return list(list_courses())

    @permission_required("training.read")
    def resolve_completions(self, info, filter=None):
        f = filter
        return list(list_completions(
            driver_id=getattr(f, "driver_id", None) if f else None,
            course_id=getattr(f, "course_id", None) if f else None,
            status=getattr(f, "status", None) if f else None,
        ))

    @permission_required("training.read")
    def resolve_driver_training(self, info, driver_id):
        driver = Driver.objects.filter(id=driver_id).first()
        if driver is None:
            return None
        return DriverTrainingType(
            completed=list(Completion.objects.filter(driver=driver).select_related("course")),
            missing=list(missing_required_courses(driver)),
        )


class Mutation(graphene.ObjectType):
    upsert_course = UpsertCourse.Field()
    delete_course = DeleteCourse.Field()
    record_completion = RecordCompletion.Field()
    delete_completion = DeleteCompletion.Field()
