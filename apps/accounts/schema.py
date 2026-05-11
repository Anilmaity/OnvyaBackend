import graphene
from graphene_django import DjangoObjectType
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import AgencyUser, Role, Permission
from apps.accounts.services import authenticate_user, write_login_event
from apps.common.graphql_types import (
    MutationResult,
    Success,
    ValidationError,
    FieldError,
)


class AgencyUserType(DjangoObjectType):
    class Meta:
        model = AgencyUser
        fields = ("id", "email", "first_name", "last_name", "phone", "is_active", "agency")


class RoleType(DjangoObjectType):
    class Meta:
        model = Role
        fields = ("id", "name", "description", "is_system")


class PermissionType(DjangoObjectType):
    class Meta:
        model = Permission
        fields = ("id", "code", "description")


class AuthPayload(graphene.ObjectType):
    access_token = graphene.String(required=True)
    refresh_token = graphene.String(required=True)
    user = graphene.Field(AgencyUserType, required=True)


class AuthResult(graphene.Union):
    class Meta:
        types = (AuthPayload, ValidationError)


class Login(graphene.Mutation):
    class Arguments:
        email = graphene.String(required=True)
        password = graphene.String(required=True)

    Output = AuthResult

    def mutate(self, info, email, password):
        request = info.context
        user = authenticate_user(email, password)
        if user is None:
            write_login_event(email_attempted=email, success=False, request=request)
            return ValidationError(field_errors=[FieldError(field="email", message="Invalid credentials")])
        write_login_event(email_attempted=email, success=True, user=user, agency=user.agency, request=request)
        refresh = RefreshToken.for_user(user)
        refresh["agency_id"] = str(user.agency_id)
        refresh["roles"] = list(user.user_roles.values_list("role__name", flat=True))
        return AuthPayload(
            access_token=str(refresh.access_token),
            refresh_token=str(refresh),
            user=user,
        )


class RefreshTokenMutation(graphene.Mutation):
    class Arguments:
        refresh_token = graphene.String(required=True)

    Output = AuthResult

    def mutate(self, info, refresh_token):
        try:
            refresh = RefreshToken(refresh_token)
            user_id = refresh.get("user_id") or refresh.get("sub")
            user = AgencyUser.all_objects.get(id=user_id)
            new_refresh = RefreshToken.for_user(user)
            new_refresh["agency_id"] = str(user.agency_id)
            new_refresh["roles"] = list(user.user_roles.values_list("role__name", flat=True))
            try:
                refresh.blacklist()
            except Exception:
                pass
            return AuthPayload(
                access_token=str(new_refresh.access_token),
                refresh_token=str(new_refresh),
                user=user,
            )
        except Exception:
            return ValidationError(
                field_errors=[FieldError(field="refresh_token", message="Invalid or expired token")]
            )


class Logout(graphene.Mutation):
    class Arguments:
        refresh_token = graphene.String(required=True)

    Output = MutationResult

    def mutate(self, info, refresh_token):
        try:
            RefreshToken(refresh_token).blacklist()
        except Exception:
            pass
        return Success(message="logged_out")


class Query(graphene.ObjectType):
    me = graphene.Field(AgencyUserType)

    def resolve_me(self, info):
        user = getattr(info.context, "user", None)
        if user and getattr(user, "is_authenticated", False):
            return user
        return None


class Mutation(graphene.ObjectType):
    login = Login.Field()
    refresh_token = RefreshTokenMutation.Field()
    logout = Logout.Field()
