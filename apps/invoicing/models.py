from decimal import Decimal

from django.db import models
from auditlog.registry import auditlog

from apps.common.models import AgencyScopedModel


class Invoice(AgencyScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        ISSUED = "ISSUED"
        PAID = "PAID"
        VOID = "VOID"

    driver = models.ForeignKey(
        "drivers.Driver", on_delete=models.PROTECT, related_name="invoices",
    )
    number = models.CharField(max_length=32)
    period_start = models.DateField()
    period_end = models.DateField()
    issued_on = models.DateField(null=True, blank=True)
    due_on = models.DateField(null=True, blank=True)
    paid_on = models.DateField(null=True, blank=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    vat = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField(blank=True, default="")

    class Meta(AgencyScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["agency", "number"], name="invoice_unique_number_per_agency",
            ),
        ]
        indexes = AgencyScopedModel.Meta.indexes + [
            models.Index(fields=["agency", "status", "period_end"]),
        ]


class InvoiceLineItem(AgencyScopedModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="line_items")
    shift = models.ForeignKey(
        "scheduling.Shift", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="invoice_lines",
    )
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=8, decimal_places=2)
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)
    amount = models.DecimalField(max_digits=10, decimal_places=2)


class InvoiceCounter(AgencyScopedModel):
    year = models.PositiveIntegerField()
    last_number = models.PositiveIntegerField(default=0)

    class Meta(AgencyScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["agency", "year"], name="invoice_counter_unique_per_year",
            ),
        ]


auditlog.register(Invoice)
auditlog.register(InvoiceLineItem)
