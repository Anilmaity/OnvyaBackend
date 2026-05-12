import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.common.context import get_current_agency
from apps.common.services import AgencyScopedService
from apps.invoicing.models import Invoice, InvoiceLineItem, InvoiceCounter
from apps.scheduling.models import Shift
from apps.scheduling.selectors import list_shifts_for_billing


VAT_RATE = Decimal(str(getattr(settings, "INVOICE_VAT_RATE", "0.20")))
DUE_DAYS = int(getattr(settings, "INVOICE_DUE_DAYS", 14))


class IllegalTransition(ValueError):
    pass


def _money(d):
    return Decimal(d).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class InvoiceService(AgencyScopedService):
    model = Invoice

    def generate_draft(self, *, driver, period_start, period_end):
        shifts = list_shifts_for_billing(
            driver=driver, period_start=period_start, period_end=period_end,
        ).exclude(
            invoice_lines__invoice__status__in=[
                Invoice.Status.DRAFT, Invoice.Status.ISSUED, Invoice.Status.PAID,
            ],
        )
        shifts = list(shifts)
        if not shifts:
            return None

        invoice = Invoice(
            driver=driver,
            number=f"DRAFT-{uuid.uuid4().hex[:8].upper()}",
            period_start=period_start,
            period_end=period_end,
            status=Invoice.Status.DRAFT,
        )
        self.save(invoice)

        subtotal = Decimal("0.00")
        line_svc = LineItemService()
        for shift in shifts:
            q = Decimal(shift.billable_hours or "0")
            p = Decimal(shift.hourly_rate or "0")
            amount = _money(q * p)
            line = InvoiceLineItem(
                invoice=invoice,
                shift=shift,
                description=f"Shift {shift.actual_start.date():%Y-%m-%d}" if shift.actual_start else f"Shift {shift.start.date():%Y-%m-%d}",
                quantity=q,
                unit_price=p,
                amount=amount,
            )
            line_svc.save(line)
            subtotal += amount

        invoice.subtotal = _money(subtotal)
        invoice.vat = _money(subtotal * VAT_RATE)
        invoice.total = _money(invoice.subtotal + invoice.vat)
        return self.save(invoice)

    def update_draft(self, invoice, line_items):
        """line_items: list of dicts {description, quantity, unit_price, shift_id?}"""
        if invoice.status != Invoice.Status.DRAFT:
            raise IllegalTransition("Only DRAFT invoices can be edited")
        invoice.line_items.all().delete()
        subtotal = Decimal("0.00")
        line_svc = LineItemService()
        for li in line_items:
            q = Decimal(li["quantity"])
            p = Decimal(li["unit_price"])
            amount = _money(q * p)
            shift = None
            if li.get("shift_id"):
                shift = Shift.objects.filter(id=li["shift_id"]).first()
            line = InvoiceLineItem(
                invoice=invoice, shift=shift,
                description=li["description"], quantity=q, unit_price=p, amount=amount,
            )
            line_svc.save(line)
            subtotal += amount
        invoice.subtotal = _money(subtotal)
        invoice.vat = _money(subtotal * VAT_RATE)
        invoice.total = _money(invoice.subtotal + invoice.vat)
        return self.save(invoice)

    @transaction.atomic
    def issue(self, invoice):
        if invoice.status != Invoice.Status.DRAFT:
            raise IllegalTransition(f"Cannot issue from state {invoice.status}")
        today = timezone.localdate()
        year = today.year
        agency = get_current_agency()
        counter, _ = InvoiceCounter.objects.select_for_update().get_or_create(
            agency=agency, year=year, defaults={"last_number": 0},
        )
        counter.last_number = counter.last_number + 1
        counter.save(update_fields=["last_number", "updated_at"])
        invoice.number = f"INV-{year}-{counter.last_number:04d}"
        invoice.status = Invoice.Status.ISSUED
        invoice.issued_on = today
        invoice.due_on = today + timedelta(days=DUE_DAYS)
        return self.save(invoice)

    def mark_paid(self, invoice, paid_on=None):
        if invoice.status != Invoice.Status.ISSUED:
            raise IllegalTransition(f"Cannot mark paid from state {invoice.status}")
        invoice.status = Invoice.Status.PAID
        invoice.paid_on = paid_on or timezone.localdate()
        return self.save(invoice)

    def void(self, invoice, reason):
        if invoice.status not in (Invoice.Status.DRAFT, Invoice.Status.ISSUED):
            raise IllegalTransition(f"Cannot void from state {invoice.status}")
        invoice.status = Invoice.Status.VOID
        invoice.notes = (invoice.notes + f"\nVOID: {reason}").strip()
        return self.save(invoice)


class LineItemService(AgencyScopedService):
    model = InvoiceLineItem
