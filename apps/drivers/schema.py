import graphene
from graphene import relay
from graphene_django import DjangoObjectType

from apps.drivers.models import Driver, DriverNote
from apps.drivers.services import DriverService, DriverNoteService
from apps.drivers.selectors import list_drivers
from apps.common.graphql_types import (
    MutationResult, Success, ValidationError, FieldError, PermissionDenied
)
from apps.common.permissions import permission_required


class DriverNoteType(DjangoObjectType):
    class Meta:
        model = DriverNote
        fields = ("id", "body", "author", "driver", "created_at")


class DriverType(DjangoObjectType):
    notes = graphene.List(graphene.NonNull(DriverNoteType), required=True)
    vehicle = graphene.Field("apps.vehicles.schema.VehicleType")

    class Meta:
        model = Driver
        fields = ("id", "first_name", "last_name", "email", "phone", "status",
                  "licence_type", "depot", "flex_enrolled", "joined_at",
                  "suspension_reason", "offboard_reason", "created_at", "updated_at",
                  "ni_number", "dbs_consent", "dbs_consent_at")

    def resolve_notes(self, info):
        return list(self.notes.all().order_by("-created_at"))

    def resolve_vehicle(self, info):
        try:
            return self.vehicle
        except Exception:
            return None


class DriverFilter(graphene.InputObjectType):
    status = graphene.String()
    depot_id = graphene.ID()
    flex_enrolled = graphene.Boolean()
    search = graphene.String()


def _validation(field, message):
    return ValidationError(field_errors=[FieldError(field=field, message=message)])


class CreateDriverInput(graphene.InputObjectType):
    first_name = graphene.String(required=True)
    last_name = graphene.String(required=True)
    email = graphene.String(required=True)
    phone = graphene.String()
    ni_number = graphene.String()
    licence_type = graphene.String()
    depot_id = graphene.ID()
    flex_enrolled = graphene.Boolean()


class CreateDriver(graphene.Mutation):
    class Arguments:
        input = CreateDriverInput(required=True)

    Output = MutationResult

    @permission_required("drivers.create")
    def mutate(self, info, input):
        if Driver.objects.filter(email=input.email.lower().strip()).exists():
            return _validation("email", "Driver with this email already exists")
        from apps.agencies.models import Depot
        depot = Depot.objects.filter(id=input.depot_id).first() if input.depot_id else None
        try:
            driver = DriverService().create(
                first_name=input.first_name,
                last_name=input.last_name,
                email=input.email,
                phone=input.phone or "",
                ni_number=input.ni_number or "",
                licence_type=input.licence_type or "",
                depot=depot,
                flex_enrolled=bool(input.flex_enrolled),
            )
        except ValueError as e:
            return _validation("non_field", str(e))
        return Success(id=str(driver.id), message="created")


class UpdateDriverInput(graphene.InputObjectType):
    first_name = graphene.String()
    last_name = graphene.String()
    phone = graphene.String()
    licence_type = graphene.String()
    depot_id = graphene.ID()
    flex_enrolled = graphene.Boolean()


class UpdateDriver(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        input = UpdateDriverInput(required=True)

    Output = MutationResult

    @permission_required("drivers.update")
    def mutate(self, info, id, input):
        driver = Driver.objects.filter(id=id).first()
        if driver is None:
            return _validation("id", "Driver not found")
        fields = {k: v for k, v in input.items() if v is not None and k != "depot_id"}
        if input.depot_id is not None:
            from apps.agencies.models import Depot
            fields["depot"] = Depot.objects.filter(id=input.depot_id).first()
        try:
            DriverService().update(driver, **fields)
        except ValueError as e:
            return _validation("non_field", str(e))
        return Success(id=str(driver.id), message="updated")


class SuspendDriver(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        reason = graphene.String(required=True)

    Output = MutationResult

    @permission_required("drivers.suspend")
    def mutate(self, info, id, reason):
        driver = Driver.objects.filter(id=id).first()
        if driver is None:
            return _validation("id", "Driver not found")
        try:
            DriverService().suspend(driver, reason)
        except ValueError as e:
            return _validation("status", str(e))
        return Success(id=str(driver.id), message="suspended")


class ReactivateDriver(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)

    Output = MutationResult

    @permission_required("drivers.suspend")
    def mutate(self, info, id):
        driver = Driver.objects.filter(id=id).first()
        if driver is None:
            return _validation("id", "Driver not found")
        try:
            DriverService().reactivate(driver)
        except ValueError as e:
            return _validation("status", str(e))
        return Success(id=str(driver.id), message="reactivated")


class OffboardDriver(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        reason = graphene.String(required=True)

    Output = MutationResult

    @permission_required("drivers.offboard")
    def mutate(self, info, id, reason):
        driver = Driver.objects.filter(id=id).first()
        if driver is None:
            return _validation("id", "Driver not found")
        try:
            DriverService().offboard(driver, reason)
        except ValueError as e:
            return _validation("status", str(e))
        return Success(id=str(driver.id), message="offboarded")


class AddDriverNote(graphene.Mutation):
    class Arguments:
        driver_id = graphene.ID(required=True)
        body = graphene.String(required=True)

    Output = MutationResult

    @permission_required("drivers.note")
    def mutate(self, info, driver_id, body):
        driver = Driver.objects.filter(id=driver_id).first()
        if driver is None:
            return _validation("driver_id", "Driver not found")
        DriverNoteService().add(driver=driver, author=info.context.user, body=body)
        return Success(message="note_added")


class Query(graphene.ObjectType):
    drivers = graphene.List(graphene.NonNull(DriverType), filter=DriverFilter(), required=True)
    driver = graphene.Field(DriverType, id=graphene.ID(required=True))

    @permission_required("drivers.read")
    def resolve_drivers(self, info, filter=None):
        f = filter
        return list(list_drivers(
            status=getattr(f, "status", None) if f else None,
            depot_id=getattr(f, "depot_id", None) if f else None,
            flex_enrolled=getattr(f, "flex_enrolled", None) if f else None,
            search=getattr(f, "search", None) if f else None,
        ))

    @permission_required("drivers.read")
    def resolve_driver(self, info, id):
        return Driver.objects.filter(id=id).first()


class Mutation(graphene.ObjectType):
    create_driver = CreateDriver.Field()
    update_driver = UpdateDriver.Field()
    suspend_driver = SuspendDriver.Field()
    reactivate_driver = ReactivateDriver.Field()
    offboard_driver = OffboardDriver.Field()
    add_driver_note = AddDriverNote.Field()
