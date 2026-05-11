import graphene


class FieldError(graphene.ObjectType):
    field = graphene.String(required=True)
    message = graphene.String(required=True)


class Success(graphene.ObjectType):
    id = graphene.ID()
    message = graphene.String()


class ValidationError(graphene.ObjectType):
    field_errors = graphene.List(graphene.NonNull(FieldError), required=True)


class PermissionDenied(graphene.ObjectType):
    code = graphene.String(required=True)
    message = graphene.String(required=True)


class MutationResult(graphene.Union):
    class Meta:
        types = (Success, ValidationError, PermissionDenied)
