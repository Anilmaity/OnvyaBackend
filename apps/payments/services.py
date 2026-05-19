import uuid
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.common.context import get_current_agency
from apps.common.services import AgencyScopedService
from apps.invoicing.models import Invoice
from apps.payments.models import (
    AgencyPaymentAccount,
    DriverBankAccount,
    PaymentStatusEvent,
    PayRun,
    PayRunItem,
)
from apps.payments.modulr import (
    ModulrError,
    PaymentInstruction,
    get_modulr_client,
)


class IllegalTransition(ValueError):
    pass


class InsufficientFunds(RuntimeError):
    pass


class MissingPaymentAccount(RuntimeError):
    pass


def _money(d) -> Decimal:
    return Decimal(d).quantize(Decimal("0.01"))


def _reference_for(driver, period_end) -> str:
    """Faster Payments reference, max 18 chars, shown on the driver's
    statement. Format: ``ONV<YYWW><LAST6>``."""
    iso = period_end.isocalendar()
    last6 = (driver.last_name or "")[:6].upper().ljust(6, "X")
    return f"ONV{iso.year % 100:02d}{iso.week:02d}{last6}"[:18]


class PayRunService(AgencyScopedService):
    model = PayRun

    # ---- build ---------------------------------------------------------- #

    def generate_draft(self, *, period_start, period_end, created_by=None):
        """Create a draft pay run from unpaid ISSUED invoices in the period."""
        agency = get_current_agency()
        invoices = list(
            Invoice.objects.filter(
                status=Invoice.Status.ISSUED,
                period_start__gte=period_start,
                period_end__lte=period_end,
            ).select_related("driver")
        )
        if not invoices:
            return None

        payrun = PayRun(
            period_start=period_start,
            period_end=period_end,
            status=PayRun.Status.DRAFT,
            created_by=created_by,
            idempotency_key=uuid.uuid4().hex,
        )
        self.save(payrun)

        item_svc = PayRunItemService()
        total = Decimal("0.00")
        count = 0
        for inv in invoices:
            bank = (
                DriverBankAccount.objects.filter(driver=inv.driver, is_primary=True, is_active=True)
                .order_by("-created_at")
                .first()
            )
            item = PayRunItem(
                payrun=payrun,
                driver=inv.driver,
                bank_account=bank,
                invoice=inv,
                amount=_money(inv.total),
                reference=_reference_for(inv.driver, period_end),
                idempotency_key=uuid.uuid4().hex,
            )
            item_svc.save(item)
            total += item.amount
            count += 1

        payrun.total_amount = _money(total)
        payrun.item_count = count
        return self.save(payrun)

    # ---- transitions ---------------------------------------------------- #

    @transaction.atomic
    def approve(self, payrun, *, approver):
        if payrun.status != PayRun.Status.DRAFT:
            raise IllegalTransition(f"Cannot approve from {payrun.status}")
        if (
            getattr(settings, "PAYMENTS_REQUIRE_FOUR_EYES", True)
            and payrun.created_by_id
            and approver
            and approver.id == payrun.created_by_id
        ):
            raise IllegalTransition("Approver must differ from creator (four-eyes rule)")
        payrun.status = PayRun.Status.APPROVED
        payrun.approved_by = approver
        payrun.approved_at = timezone.now()
        return self.save(payrun)

    @transaction.atomic
    def submit(self, payrun, *, submitter):
        if payrun.status != PayRun.Status.APPROVED:
            raise IllegalTransition(f"Cannot submit from {payrun.status}")

        account = (
            AgencyPaymentAccount.objects.filter(is_active=True).first()
        )
        if account is None:
            raise MissingPaymentAccount(
                "Agency has no active payment account; complete Modulr setup."
            )

        client = get_modulr_client()
        balance = client.get_account_balance(account.provider_account_id)
        if balance.available < payrun.total_amount:
            raise InsufficientFunds(
                f"Modulr balance {balance.available} < required {payrun.total_amount}"
            )

        items = list(payrun.items.select_related("bank_account").all())
        instructions = []
        for it in items:
            if it.bank_account is None:
                it.status = PayRunItem.Status.FAILED
                it.failure_reason = "No bank account on file"
                PayRunItemService().save(it)
                continue
            instructions.append(PaymentInstruction(
                reference=it.reference,
                amount=it.amount,
                destination_sort_code=it.bank_account.sort_code,
                destination_account_number=it.bank_account.account_number,
                destination_account_name=it.bank_account.account_holder_name,
                external_reference=it.idempotency_key,
            ))

        if not instructions:
            payrun.status = PayRun.Status.FAILED
            payrun.failure_reason = "No payable items"
            return self.save(payrun)

        try:
            result = client.submit_batch(
                provider_account_id=account.provider_account_id,
                instructions=instructions,
                batch_idempotency_key=payrun.idempotency_key,
            )
        except ModulrError as e:
            payrun.status = PayRun.Status.FAILED
            payrun.failure_reason = str(e)[:2000]
            return self.save(payrun)

        payrun.provider_batch_id = result.provider_batch_id
        payrun.status = PayRun.Status.SUBMITTED
        payrun.submitted_by = submitter
        payrun.submitted_at = timezone.now()
        self.save(payrun)

        for it in items:
            if it.status == PayRunItem.Status.FAILED:
                continue
            it.status = PayRunItem.Status.SUBMITTED
            PayRunItemService().save(it)

        PaymentStatusEvent.objects.create(
            agency=get_current_agency(),
            payrun=payrun,
            event_type="batch.submitted",
            payload=result.raw,
        )
        return payrun

    def cancel(self, payrun, *, reason=""):
        if payrun.status not in (PayRun.Status.DRAFT, PayRun.Status.APPROVED):
            raise IllegalTransition(f"Cannot cancel from {payrun.status}")
        payrun.status = PayRun.Status.CANCELLED
        payrun.failure_reason = reason
        return self.save(payrun)

    # ---- reconciliation ------------------------------------------------- #

    @transaction.atomic
    def apply_item_status(self, item, *, status, provider_payment_id="",
                          failure_reason="", paid_at=None):
        """Apply a terminal status from a webhook or reconciliation poll."""
        if item.status in (PayRunItem.Status.PAID, PayRunItem.Status.RETURNED):
            return item  # idempotent
        item.status = status
        if provider_payment_id:
            item.provider_payment_id = provider_payment_id
        if status == PayRunItem.Status.PAID:
            item.paid_at = paid_at or timezone.now()
            if item.invoice_id:
                Invoice.objects.filter(id=item.invoice_id).update(
                    status=Invoice.Status.PAID,
                    paid_on=(paid_at or timezone.now()).date(),
                )
        if failure_reason:
            item.failure_reason = failure_reason[:2000]
        PayRunItemService().save(item)
        self._roll_up_payrun(item.payrun)
        return item

    def _roll_up_payrun(self, payrun):
        statuses = set(payrun.items.values_list("status", flat=True))
        if not statuses or statuses & {PayRunItem.Status.PENDING, PayRunItem.Status.SUBMITTED}:
            return
        if statuses == {PayRunItem.Status.PAID}:
            payrun.status = PayRun.Status.COMPLETED
        elif statuses <= {PayRunItem.Status.FAILED, PayRunItem.Status.RETURNED}:
            payrun.status = PayRun.Status.FAILED
        else:
            payrun.status = PayRun.Status.COMPLETED
        self.save(payrun)


class PayRunItemService(AgencyScopedService):
    model = PayRunItem


class AgencyPaymentAccountService(AgencyScopedService):
    model = AgencyPaymentAccount


class DriverBankAccountService(AgencyScopedService):
    model = DriverBankAccount

    def run_cop(self, bank_account):
        client = get_modulr_client()
        result = client.confirmation_of_payee(
            sort_code=bank_account.sort_code,
            account_number=bank_account.account_number,
            account_name=bank_account.account_holder_name,
        )
        bank_account.cop_status = result
        bank_account.cop_checked_at = timezone.now()
        return self.save(bank_account)
