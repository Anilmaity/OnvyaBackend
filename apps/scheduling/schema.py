import graphene
from graphene_django import DjangoObjectType

from apps.common.graphql_types import (
    MutationResult, Success, ValidationError, FieldError,
)
from apps.common.permissions import permission_required
from apps.drivers.models import Driver
from apps.agencies.models import Depot
from apps.scheduling.models import Shift, TimeAdjustment
from apps.scheduling.services import (
    ShiftService, TimeAdjustmentService, IllegalTransition, IllegalAdjustment,
)
from apps.scheduling.selectors import list_shifts, list_time_adjustments


def _validation(field, message):
    return ValidationError(field_errors=[FieldError(field=field, message=message)])


class ShiftType(DjangoObjectType):
    adjustments = graphene.List(graphene.NonNull(lambda: TimeAdjustmentType), required=True)

    class Meta:
        model = Shift
        fields = (
            "id", "driver", "depot", "start", "end",
            "actual_start", "actual_end", "status", "notes",
            "billable_hours", "hourly_rate", "created_at", "updated_at",
        )

    def resolve_adjustments(self, info):
        return list(self.adjustments.all().order_by("-created_at"))


class TimeAdjustmentType(DjangoObjectType):
    class Meta:
        model = TimeAdjustment
        fields = (
            "id", "shift", "requested_by", "decided_by",
            "proposed_start", "proposed_end", "reason", "state",
            "decided_at", "decision_note", "created_at", "updated_at",
        )


class ShiftFilter(graphene.InputObjectType):
    driver_id = graphene.ID()
    depot_id = graphene.ID()
    status = graphene.String()
    start_after = graphene.DateTime()
    start_before = graphene.DateTime()


class TimeAdjustmentFilter(graphene.InputObjectType):
    shift_id = graphene.ID()
    state = graphene.String()


class CreateShiftInput(graphene.InputObjectType):
    driver_id = graphene.ID(required=True)
    depot_id = graphene.ID()
    start = graphene.DateTime(required=True)
    end = graphene.DateTime(required=True)
    notes = graphene.String()


class CreateShift(graphene.Mutation):
    class Arguments:
        input = CreateShiftInput(required=True)
    Output = MutationResult

    @permission_required("scheduling.create")
    def mutate(self, info, input):
        driver = Driver.objects.filter(id=input.driver_id).first()
        if driver is None:
            return _validation("driver_id", "Driver not found")
        depot = Depot.objects.filter(id=input.depot_id).first() if input.depot_id else None
        try:
            shift = ShiftService().create(
                driver=driver, depot=depot, start=input.start, end=input.end,
                notes=input.notes or "",
            )
        except IllegalTransition as e:
            return _validation("state", str(e))
        return Success(id=str(shift.id), message="created")


class UpdateShiftInput(graphene.InputObjectType):
    start = graphene.DateTime()
    end = graphene.DateTime()
    depot_id = graphene.ID()
    notes = graphene.String()


class UpdateShift(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        input = UpdateShiftInput(required=True)
    Output = MutationResult

    @permission_required("scheduling.update")
    def mutate(self, info, id, input):
        shift = Shift.objects.filter(id=id).first()
        if shift is None:
            return _validation("id", "Shift not found")
        fields = {}
        if input.start is not None:
            fields["start"] = input.start
        if input.end is not None:
            fields["end"] = input.end
        if input.notes is not None:
            fields["notes"] = input.notes
        if input.depot_id is not None:
            fields["depot"] = Depot.objects.filter(id=input.depot_id).first()
        try:
            ShiftService().update(shift, **fields)
        except IllegalTransition as e:
            return _validation("state", str(e))
        return Success(id=str(shift.id), message="updated")


class CancelShift(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
    Output = MutationResult

    @permission_required("scheduling.update")
    def mutate(self, info, id):
        shift = Shift.objects.filter(id=id).first()
        if shift is None:
            return _validation("id", "Shift not found")
        try:
            ShiftService().cancel(shift)
        except IllegalTransition as e:
            return _validation("state", str(e))
        return Success(id=str(shift.id), message="cancelled")


class CompleteShift(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        actual_start = graphene.DateTime()
        actual_end = graphene.DateTime()
    Output = MutationResult

    @permission_required("scheduling.update")
    def mutate(self, info, id, actual_start=None, actual_end=None):
        shift = Shift.objects.filter(id=id).first()
        if shift is None:
            return _validation("id", "Shift not found")
        try:
            ShiftService().complete(shift, actual_start=actual_start, actual_end=actual_end)
        except IllegalTransition as e:
            return _validation("state", str(e))
        return Success(id=str(shift.id), message="completed")


class RequestTimeAdjustmentInput(graphene.InputObjectType):
    shift_id = graphene.ID(required=True)
    proposed_start = graphene.DateTime(required=True)
    proposed_end = graphene.DateTime(required=True)
    reason = graphene.String(required=True)


class RequestTimeAdjustment(graphene.Mutation):
    class Arguments:
        input = RequestTimeAdjustmentInput(required=True)
    Output = MutationResult

    @permission_required("scheduling.update")
    def mutate(self, info, input):
        shift = Shift.objects.filter(id=input.shift_id).first()
        if shift is None:
            return _validation("shift_id", "Shift not found")
        try:
            adj = TimeAdjustmentService().request(
                shift=shift, user=info.context.user,
                proposed_start=input.proposed_start,
                proposed_end=input.proposed_end,
                reason=input.reason,
            )
        except IllegalAdjustment as e:
            return _validation("state", str(e))
        return Success(id=str(adj.id), message="requested")


class ApproveTimeAdjustment(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        decision_note = graphene.String()
    Output = MutationResult

    @permission_required("scheduling.approve_adjustment")
    def mutate(self, info, id, decision_note=None):
        adj = TimeAdjustment.objects.filter(id=id).first()
        if adj is None:
            return _validation("id", "Adjustment not found")
        try:
            TimeAdjustmentService().approve(adj, info.context.user, decision_note or "")
        except IllegalAdjustment as e:
            return _validation("state", str(e))
        return Success(id=str(adj.id), message="approved")


class RejectTimeAdjustment(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        decision_note = graphene.String(required=True)
    Output = MutationResult

    @permission_required("scheduling.approve_adjustment")
    def mutate(self, info, id, decision_note):
        adj = TimeAdjustment.objects.filter(id=id).first()
        if adj is None:
            return _validation("id", "Adjustment not found")
        try:
            TimeAdjustmentService().reject(adj, info.context.user, decision_note)
        except IllegalAdjustment as e:
            return _validation("state", str(e))
        return Success(id=str(adj.id), message="rejected")


class Query(graphene.ObjectType):
    shifts = graphene.List(
        graphene.NonNull(ShiftType), filter=ShiftFilter(), required=True,
    )
    shift = graphene.Field(ShiftType, id=graphene.ID(required=True))
    my_shifts = graphene.List(graphene.NonNull(ShiftType), required=True)
    time_adjustments = graphene.List(
        graphene.NonNull(TimeAdjustmentType), filter=TimeAdjustmentFilter(), required=True,
    )
    time_adjustment = graphene.Field(TimeAdjustmentType, id=graphene.ID(required=True))

    @permission_required("scheduling.read")
    def resolve_shifts(self, info, filter=None):
        f = filter
        return list(list_shifts(
            driver_id=getattr(f, "driver_id", None) if f else None,
            depot_id=getattr(f, "depot_id", None) if f else None,
            status=getattr(f, "status", None) if f else None,
            start_after=getattr(f, "start_after", None) if f else None,
            start_before=getattr(f, "start_before", None) if f else None,
        ))

    def resolve_my_shifts(self, info):
        user = getattr(info.context, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return []
        driver = getattr(user, "driver_profile", None)
        if driver is None:
            return []
        return list(Shift.objects.filter(driver=driver).order_by("-start"))

    @permission_required("scheduling.read")
    def resolve_shift(self, info, id):
        return Shift.objects.filter(id=id).first()

    @permission_required("scheduling.read")
    def resolve_time_adjustments(self, info, filter=None):
        f = filter
        return list(list_time_adjustments(
            shift_id=getattr(f, "shift_id", None) if f else None,
            state=getattr(f, "state", None) if f else None,
        ))

    @permission_required("scheduling.read")
    def resolve_time_adjustment(self, info, id):
        return TimeAdjustment.objects.filter(id=id).first()


class Mutation(graphene.ObjectType):
    create_shift = CreateShift.Field()
    update_shift = UpdateShift.Field()
    cancel_shift = CancelShift.Field()
    complete_shift = CompleteShift.Field()
    request_time_adjustment = RequestTimeAdjustment.Field()
    approve_time_adjustment = ApproveTimeAdjustment.Field()
    reject_time_adjustment = RejectTimeAdjustment.Field()
