from decimal import Decimal

from django.db import models
from auditlog.registry import auditlog

from apps.common.models import AgencyScopedModel


class PaymentProvider(models.TextChoices):
    MODULR = "MODULR"
    # Reserved for future BaaS providers (ClearBank, Railsr, Griffin).


class AgencyPaymentAccount(AgencyScopedModel):
    """The agency's own e-money account at a BaaS provider.

    Onvya never owns this account — it stores only a reference so the
    platform can issue API instructions on the agency's behalf.
    """

    provider = models.CharField(
        max_length=16, choices=PaymentProvider.choices, default=PaymentProvider.MODULR,
    )
    provider_customer_id = models.CharField(max_length=64, blank=True, default="")
    provider_account_id = models.CharField(max_length=64)
    sort_code = models.CharField(max_length=8, blank=True, default="")
    account_number = models.CharField(max_length=12, blank=True, default="")
    account_name = models.CharField(max_length=120, blank=True, default="")
    last_known_balance = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00"),
    )
    last_balance_synced_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(AgencyScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["agency", "provider"],
                name="payment_account_one_per_provider_per_agency",
            ),
        ]


class DriverBankAccount(AgencyScopedModel):
    """Driver payee details. Account number is the only PII we hold; the
    long-term plan is to tokenise these through Modulr's beneficiary API
    so we never store raw account numbers."""

    driver = models.ForeignKey(
        "drivers.Driver", on_delete=models.CASCADE, related_name="bank_accounts",
    )
    account_holder_name = models.CharField(max_length=120)
    sort_code = models.CharField(max_length=8)
    account_number = models.CharField(max_length=12)
    is_primary = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    cop_status = models.CharField(max_length=16, blank=True, default="")  # MATCH/CLOSE/NO_MATCH
    cop_checked_at = models.DateTimeField(null=True, blank=True)
    provider_beneficiary_id = models.CharField(max_length=64, blank=True, default="")

    class Meta(AgencyScopedModel.Meta):
        indexes = AgencyScopedModel.Meta.indexes + [
            models.Index(fields=["agency", "driver", "is_primary"]),
        ]


class PayRun(AgencyScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        APPROVED = "APPROVED"
        SUBMITTED = "SUBMITTED"
        COMPLETED = "COMPLETED"
        FAILED = "FAILED"
        CANCELLED = "CANCELLED"

    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT,
    )
    total_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00"),
    )
    item_count = models.PositiveIntegerField(default=0)

    created_by = models.ForeignKey(
        "accounts.AgencyUser", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="payruns_created",
    )
    approved_by = models.ForeignKey(
        "accounts.AgencyUser", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="payruns_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        "accounts.AgencyUser", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="payruns_submitted",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)

    provider_batch_id = models.CharField(max_length=64, blank=True, default="")
    idempotency_key = models.CharField(max_length=64, blank=True, default="")
    failure_reason = models.TextField(blank=True, default="")

    class Meta(AgencyScopedModel.Meta):
        indexes = AgencyScopedModel.Meta.indexes + [
            models.Index(fields=["agency", "status", "period_end"]),
        ]


class PayRunItem(AgencyScopedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING"
        SUBMITTED = "SUBMITTED"
        PAID = "PAID"
        FAILED = "FAILED"
        RETURNED = "RETURNED"

    payrun = models.ForeignKey(
        PayRun, on_delete=models.CASCADE, related_name="items",
    )
    driver = models.ForeignKey(
        "drivers.Driver", on_delete=models.PROTECT, related_name="payrun_items",
    )
    bank_account = models.ForeignKey(
        DriverBankAccount, on_delete=models.PROTECT, related_name="payrun_items",
        null=True, blank=True,
    )
    invoice = models.ForeignKey(
        "invoicing.Invoice", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="payrun_items",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reference = models.CharField(max_length=18, blank=True, default="")
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING,
    )
    provider_payment_id = models.CharField(max_length=64, blank=True, default="")
    idempotency_key = models.CharField(max_length=64, blank=True, default="")
    paid_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True, default="")

    class Meta(AgencyScopedModel.Meta):
        indexes = AgencyScopedModel.Meta.indexes + [
            models.Index(fields=["agency", "payrun", "status"]),
            models.Index(fields=["agency", "provider_payment_id"]),
        ]


class PaymentStatusEvent(AgencyScopedModel):
    """Append-only ledger of webhook + reconciliation events from the
    provider. We never mutate these; they are the audit spine for any
    dispute."""

    item = models.ForeignKey(
        PayRunItem, on_delete=models.CASCADE, related_name="events",
        null=True, blank=True,
    )
    payrun = models.ForeignKey(
        PayRun, on_delete=models.CASCADE, related_name="events",
        null=True, blank=True,
    )
    event_type = models.CharField(max_length=64)
    provider_event_id = models.CharField(max_length=80, blank=True, default="")
    payload = models.JSONField(default=dict)

    class Meta(AgencyScopedModel.Meta):
        indexes = AgencyScopedModel.Meta.indexes + [
            models.Index(fields=["agency", "event_type", "created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["agency", "provider_event_id"],
                name="payment_event_unique_per_agency",
                condition=models.Q(provider_event_id__gt=""),
            ),
        ]


auditlog.register(AgencyPaymentAccount)
auditlog.register(DriverBankAccount, exclude_fields=["account_number"])
auditlog.register(PayRun)
auditlog.register(PayRunItem)
