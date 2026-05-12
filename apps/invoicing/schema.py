import graphene
from graphene_django import DjangoObjectType

from apps.common.graphql_types import MutationResult, Success, ValidationError, FieldError
from apps.common.permissions import permission_required
from apps.drivers.models import Driver
from apps.invoicing.models import Invoice, InvoiceLineItem
from apps.invoicing.services import InvoiceService, IllegalTransition
from apps.invoicing.selectors import list_invoices


def _validation(field, message):
    return ValidationError(field_errors=[FieldError(field=field, message=message)])


class InvoiceLineItemType(DjangoObjectType):
    class Meta:
        model = InvoiceLineItem
        fields = ("id", "invoice", "shift", "description", "quantity", "unit_price", "amount")


class InvoiceType(DjangoObjectType):
    line_items = graphene.List(graphene.NonNull(InvoiceLineItemType), required=True)

    class Meta:
        model = Invoice
        fields = ("id", "driver", "number", "period_start", "period_end",
                  "issued_on", "due_on", "paid_on", "subtotal", "vat", "total",
                  "status", "notes", "created_at", "updated_at")

    def resolve_line_items(self, info):
        return list(self.line_items.all())


class InvoiceFilter(graphene.InputObjectType):
    driver_id = graphene.ID()
    status = graphene.String()
    period_start_after = graphene.Date()
    period_end_before = graphene.Date()


class GenerateDraftInvoiceInput(graphene.InputObjectType):
    driver_id = graphene.ID(required=True)
    period_start = graphene.Date(required=True)
    period_end = graphene.Date(required=True)


class GenerateDraftInvoice(graphene.Mutation):
    class Arguments:
        input = GenerateDraftInvoiceInput(required=True)
    Output = MutationResult

    @permission_required("invoicing.create")
    def mutate(self, info, input):
        driver = Driver.objects.filter(id=input.driver_id).first()
        if driver is None:
            return _validation("driver_id", "Driver not found")
        invoice = InvoiceService().generate_draft(
            driver=driver,
            period_start=input.period_start,
            period_end=input.period_end,
        )
        if invoice is None:
            return _validation("period", "No completed shifts in this period")
        return Success(id=str(invoice.id), message="drafted")


class IssueInvoice(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
    Output = MutationResult

    @permission_required("invoicing.update")
    def mutate(self, info, id):
        invoice = Invoice.objects.filter(id=id).first()
        if invoice is None:
            return _validation("id", "Invoice not found")
        try:
            InvoiceService().issue(invoice)
        except IllegalTransition as e:
            return _validation("state", str(e))
        return Success(id=str(invoice.id), message="issued")


class MarkInvoicePaid(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        paid_on = graphene.Date()
    Output = MutationResult

    @permission_required("invoicing.update")
    def mutate(self, info, id, paid_on=None):
        invoice = Invoice.objects.filter(id=id).first()
        if invoice is None:
            return _validation("id", "Invoice not found")
        try:
            InvoiceService().mark_paid(invoice, paid_on)
        except IllegalTransition as e:
            return _validation("state", str(e))
        return Success(id=str(invoice.id), message="paid")


class VoidInvoice(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        reason = graphene.String(required=True)
    Output = MutationResult

    @permission_required("invoicing.update")
    def mutate(self, info, id, reason):
        invoice = Invoice.objects.filter(id=id).first()
        if invoice is None:
            return _validation("id", "Invoice not found")
        try:
            InvoiceService().void(invoice, reason)
        except IllegalTransition as e:
            return _validation("state", str(e))
        return Success(id=str(invoice.id), message="voided")


class Query(graphene.ObjectType):
    invoices = graphene.List(
        graphene.NonNull(InvoiceType), filter=InvoiceFilter(), required=True,
    )
    invoice = graphene.Field(InvoiceType, id=graphene.ID(required=True))

    @permission_required("invoicing.read")
    def resolve_invoices(self, info, filter=None):
        f = filter
        return list(list_invoices(
            driver_id=getattr(f, "driver_id", None) if f else None,
            status=getattr(f, "status", None) if f else None,
            period_start_after=getattr(f, "period_start_after", None) if f else None,
            period_end_before=getattr(f, "period_end_before", None) if f else None,
        ))

    @permission_required("invoicing.read")
    def resolve_invoice(self, info, id):
        return Invoice.objects.filter(id=id).first()


class Mutation(graphene.ObjectType):
    generate_draft_invoice = GenerateDraftInvoice.Field()
    issue_invoice = IssueInvoice.Field()
    mark_invoice_paid = MarkInvoicePaid.Field()
    void_invoice = VoidInvoice.Field()
