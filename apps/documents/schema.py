import graphene
from graphene_django import DjangoObjectType

from apps.common.graphql_types import MutationResult, Success, ValidationError, FieldError
from apps.common.permissions import permission_required
from apps.drivers.models import Driver
from apps.documents.models import DriverDocument
from apps.documents.services import DocumentService
from apps.documents.selectors import list_documents


def _validation(field, message):
    return ValidationError(field_errors=[FieldError(field=field, message=message)])


class DriverDocumentType(DjangoObjectType):
    class Meta:
        model = DriverDocument
        fields = (
            "id", "driver", "kind", "reference", "issued_on", "expires_on",
            "status", "notes", "created_at", "updated_at",
        )


class DriverDocumentFilter(graphene.InputObjectType):
    driver_id = graphene.ID()
    kind = graphene.String()
    status = graphene.String()
    expires_before = graphene.Date()


class UpsertDriverDocumentInput(graphene.InputObjectType):
    driver_id = graphene.ID(required=True)
    kind = graphene.String(required=True)
    reference = graphene.String()
    issued_on = graphene.Date()
    expires_on = graphene.Date()
    notes = graphene.String()


class UpsertDriverDocument(graphene.Mutation):
    class Arguments:
        input = UpsertDriverDocumentInput(required=True)
    Output = MutationResult

    @permission_required("documents.write")
    def mutate(self, info, input):
        driver = Driver.objects.filter(id=input.driver_id).first()
        if driver is None:
            return _validation("driver_id", "Driver not found")
        doc = DocumentService().upsert(
            driver=driver,
            kind=input.kind,
            reference=input.reference or "",
            issued_on=input.issued_on,
            expires_on=input.expires_on,
            notes=input.notes or "",
        )
        return Success(id=str(doc.id), message="upserted")


class DeleteDriverDocument(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
    Output = MutationResult

    @permission_required("documents.write")
    def mutate(self, info, id):
        doc = DriverDocument.objects.filter(id=id).first()
        if doc is None:
            return _validation("id", "Document not found")
        doc.delete()
        return Success(id=str(id), message="deleted")


class Query(graphene.ObjectType):
    driver_documents = graphene.List(
        graphene.NonNull(DriverDocumentType), filter=DriverDocumentFilter(), required=True,
    )
    driver_document = graphene.Field(DriverDocumentType, id=graphene.ID(required=True))

    @permission_required("documents.read")
    def resolve_driver_documents(self, info, filter=None):
        f = filter
        return list(list_documents(
            driver_id=getattr(f, "driver_id", None) if f else None,
            kind=getattr(f, "kind", None) if f else None,
            status=getattr(f, "status", None) if f else None,
            expires_before=getattr(f, "expires_before", None) if f else None,
        ))

    @permission_required("documents.read")
    def resolve_driver_document(self, info, id):
        return DriverDocument.objects.filter(id=id).first()


class Mutation(graphene.ObjectType):
    upsert_driver_document = UpsertDriverDocument.Field()
    delete_driver_document = DeleteDriverDocument.Field()
