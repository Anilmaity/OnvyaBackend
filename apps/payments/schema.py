import graphene
from graphene_django import DjangoObjectType

from apps.common.graphql_types import (
    FieldError,
    MutationResult,
    PermissionDenied,
    Success,
    ValidationError,
)
from apps.common.permissions import permission_required
from apps.drivers.models import Driver
from apps.payments.models import (
    AgencyPaymentAccount,
    DriverBankAccount,
    PayRun,
    PayRunItem,
)
from apps.payments.selectors import list_payrun_items, list_payruns
from apps.payments.services import (
    AgencyPaymentAccountService,
    DriverBankAccountService,
    IllegalTransition,
    InsufficientFunds,
    MissingPaymentAccount,
    PayRunService,
)


def _validation(field, message):
    return ValidationError(field_errors=[FieldError(field=field, message=message)])


# --- types ---------------------------------------------------------------- #


class AgencyPaymentAccountType(DjangoObjectType):
    class Meta:
        model = AgencyPaymentAccount
        fields = (
            "id", "provider", "provider_account_id", "sort_code", "account_number",
            "account_name", "last_known_balance", "last_balance_synced_at",
            "is_active", "created_at", "updated_at",
        )


class DriverBankAccountType(DjangoObjectType):
    class Meta:
        model = DriverBankAccount
        fields = (
            "id", "driver", "account_holder_name", "sort_code", "account_number",
            "is_primary", "is_active", "cop_status", "cop_checked_at",
            "created_at", "updated_at",
        )


class PayRunItemType(DjangoObjectType):
    class Meta:
        model = PayRunItem
        fields = (
            "id", "payrun", "driver", "bank_account", "invoice", "amount",
            "reference", "status", "provider_payment_id", "paid_at",
            "failure_reason", "created_at", "updated_at",
        )


class PayRunType(DjangoObjectType):
    items = graphene.List(graphene.NonNull(PayRunItemType), required=True)

    class Meta:
        model = PayRun
        fields = (
            "id", "period_start", "period_end", "status", "total_amount",
            "item_count", "created_by", "approved_by", "approved_at",
            "submitted_by", "submitted_at", "provider_batch_id",
            "failure_reason", "created_at", "updated_at",
        )

    def resolve_items(self, info):
        return list(list_payrun_items(self.id))


# --- inputs --------------------------------------------------------------- #


class PayRunFilter(graphene.InputObjectType):
    status = graphene.String()
    period_start_after = graphene.Date()
    period_end_before = graphene.Date()


class GenerateDraftPayRunInput(graphene.InputObjectType):
    period_start = graphene.Date(required=True)
    period_end = graphene.Date(required=True)


class UpsertDriverBankAccountInput(graphene.InputObjectType):
    driver_id = graphene.ID(required=True)
    account_holder_name = graphene.String(required=True)
    sort_code = graphene.String(required=True)
    account_number = graphene.String(required=True)
    run_cop = graphene.Boolean(default_value=True)


class UpsertAgencyPaymentAccountInput(graphene.InputObjectType):
    provider_account_id = graphene.String(required=True)
    provider_customer_id = graphene.String()
    sort_code = graphene.String()
    account_number = graphene.String()
    account_name = graphene.String()


# --- mutations ------------------------------------------------------------ #


class GenerateDraftPayRun(graphene.Mutation):
    class Arguments:
        input = GenerateDraftPayRunInput(required=True)

    Output = MutationResult

    @permission_required("payments.calculate")
    def mutate(self, info, input):
        payrun = PayRunService().generate_draft(
            period_start=input.period_start,
            period_end=input.period_end,
            created_by=getattr(info.context, "user", None),
        )
        if payrun is None:
            return _validation("period", "No ISSUED invoices in this period")
        return Success(id=str(payrun.id), message="drafted")


class ApprovePayRun(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)

    Output = MutationResult

    @permission_required("payments.approve")
    def mutate(self, info, id):
        payrun = PayRun.objects.filter(id=id).first()
        if payrun is None:
            return _validation("id", "PayRun not found")
        try:
            PayRunService().approve(payrun, approver=info.context.user)
        except IllegalTransition as e:
            return _validation("state", str(e))
        return Success(id=str(payrun.id), message="approved")


class SubmitPayRun(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)

    Output = MutationResult

    @permission_required("payments.submit")
    def mutate(self, info, id):
        payrun = PayRun.objects.filter(id=id).first()
        if payrun is None:
            return _validation("id", "PayRun not found")
        try:
            PayRunService().submit(payrun, submitter=info.context.user)
        except (IllegalTransition, InsufficientFunds, MissingPaymentAccount) as e:
            return _validation("state", str(e))
        if payrun.status == PayRun.Status.FAILED:
            return _validation("submission", payrun.failure_reason or "Submission failed")
        return Success(id=str(payrun.id), message="submitted")


class CancelPayRun(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        reason = graphene.String()

    Output = MutationResult

    @permission_required("payments.approve")
    def mutate(self, info, id, reason=""):
        payrun = PayRun.objects.filter(id=id).first()
        if payrun is None:
            return _validation("id", "PayRun not found")
        try:
            PayRunService().cancel(payrun, reason=reason or "")
        except IllegalTransition as e:
            return _validation("state", str(e))
        return Success(id=str(payrun.id), message="cancelled")


class UpsertDriverBankAccount(graphene.Mutation):
    class Arguments:
        input = UpsertDriverBankAccountInput(required=True)

    Output = MutationResult

    def mutate(self, info, input):
        user = getattr(info.context, "user", None)
        driver = Driver.objects.filter(id=input.driver_id).first()
        if driver is None:
            return _validation("driver_id", "Driver not found")
        # Allow self-service: a driver can update their own bank account.
        # Otherwise require the admin-side drivers.update permission.
        is_self = user is not None and getattr(user, "driver_profile", None) is not None and str(user.driver_profile.id) == str(driver.id)
        if not is_self:
            from apps.common.permissions import has_permission
            if not has_permission(user, "drivers.update"):
                return PermissionDenied(code="permission_denied", message="drivers.update required")
        svc = DriverBankAccountService()
        existing = DriverBankAccount.objects.filter(driver=driver, is_primary=True).first()
        if existing:
            existing.account_holder_name = input.account_holder_name
            existing.sort_code = input.sort_code
            existing.account_number = input.account_number
            existing.is_active = True
            account = svc.save(existing)
        else:
            account = svc.save(DriverBankAccount(
                driver=driver,
                account_holder_name=input.account_holder_name,
                sort_code=input.sort_code,
                account_number=input.account_number,
                is_primary=True,
            ))
        if input.run_cop:
            try:
                svc.run_cop(account)
            except Exception:
                pass  # CoP failure must not block save; surfaced via status field
        return Success(id=str(account.id), message="saved")


class UpsertAgencyPaymentAccount(graphene.Mutation):
    class Arguments:
        input = UpsertAgencyPaymentAccountInput(required=True)

    Output = MutationResult

    @permission_required("payments.configure")
    def mutate(self, info, input):
        svc = AgencyPaymentAccountService()
        account = AgencyPaymentAccount.objects.filter(is_active=True).first()
        if account:
            account.provider_account_id = input.provider_account_id
            account.provider_customer_id = input.provider_customer_id or account.provider_customer_id
            account.sort_code = input.sort_code or account.sort_code
            account.account_number = input.account_number or account.account_number
            account.account_name = input.account_name or account.account_name
            account = svc.save(account)
        else:
            account = svc.save(AgencyPaymentAccount(
                provider_account_id=input.provider_account_id,
                provider_customer_id=input.provider_customer_id or "",
                sort_code=input.sort_code or "",
                account_number=input.account_number or "",
                account_name=input.account_name or "",
            ))
        return Success(id=str(account.id), message="saved")


# --- root ----------------------------------------------------------------- #


class Query(graphene.ObjectType):
    payruns = graphene.List(
        graphene.NonNull(PayRunType), filter=PayRunFilter(), required=True,
    )
    payrun = graphene.Field(PayRunType, id=graphene.ID(required=True))
    agency_payment_account = graphene.Field(AgencyPaymentAccountType)

    @permission_required("payments.read")
    def resolve_payruns(self, info, filter=None):
        f = filter
        return list(list_payruns(
            status=getattr(f, "status", None) if f else None,
            period_start_after=getattr(f, "period_start_after", None) if f else None,
            period_end_before=getattr(f, "period_end_before", None) if f else None,
        ))

    @permission_required("payments.read")
    def resolve_payrun(self, info, id):
        return PayRun.objects.filter(id=id).first()

    @permission_required("payments.read")
    def resolve_agency_payment_account(self, info):
        return AgencyPaymentAccount.objects.filter(is_active=True).first()


class Mutation(graphene.ObjectType):
    generate_draft_payrun = GenerateDraftPayRun.Field()
    approve_payrun = ApprovePayRun.Field()
    submit_payrun = SubmitPayRun.Field()
    cancel_payrun = CancelPayRun.Field()
    upsert_driver_bank_account = UpsertDriverBankAccount.Field()
    upsert_agency_payment_account = UpsertAgencyPaymentAccount.Field()
