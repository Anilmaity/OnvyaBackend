import graphene
from graphene_django import DjangoObjectType
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import AgencyUser, Role, Permission, RolePermission, UserRole
from apps.accounts.services import authenticate_user, write_login_event
from apps.common.graphql_types import (
    MutationResult,
    Success,
    ValidationError,
    FieldError,
)


class RoleType(DjangoObjectType):
    class Meta:
        model = Role
        fields = ("id", "name", "description", "is_system")


class PermissionType(DjangoObjectType):
    class Meta:
        model = Permission
        fields = ("id", "code", "description")


class AgencyUserType(DjangoObjectType):
    permissions = graphene.List(graphene.NonNull(graphene.String), required=True)
    roles = graphene.List(graphene.NonNull(RoleType), required=True)

    class Meta:
        model = AgencyUser
        fields = ("id", "email", "first_name", "last_name", "phone", "is_active", "agency")

    def resolve_permissions(self, info):
        codes = set(
            self.user_roles.values_list("role__role_permissions__permission__code", flat=True)
        )
        codes.discard(None)
        return sorted(codes)

    def resolve_roles(self, info):
        return [ur.role for ur in self.user_roles.select_related("role").all()]


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


class CreateAgencyUserInput(graphene.InputObjectType):
    email = graphene.String(required=True)
    first_name = graphene.String(required=True)
    last_name = graphene.String(required=True)
    phone = graphene.String()
    password = graphene.String(required=True)
    role_ids = graphene.List(graphene.NonNull(graphene.ID), required=True)


def _validation(field, message):
    return ValidationError(field_errors=[FieldError(field=field, message=message)])


class CreateAgencyUser(graphene.Mutation):
    class Arguments:
        input = CreateAgencyUserInput(required=True)

    Output = MutationResult

    def mutate(self, info, input):
        from apps.common.permissions import has_permission
        from apps.common.graphql_types import PermissionDenied
        actor = getattr(info.context, "user", None)
        if not has_permission(actor, "accounts.manage"):
            return PermissionDenied(code="permission_denied", message="Missing permission: accounts.manage")
        from apps.common.context import get_current_agency
        agency = get_current_agency()
        email = input.email.lower().strip()
        if AgencyUser.objects.filter(email=email).exists():
            return _validation("email", "User with this email already exists in this agency")
        user = AgencyUser(
            agency=agency, email=email,
            first_name=input.first_name, last_name=input.last_name,
            phone=input.phone or "", is_active=True,
        )
        user.set_password(input.password)
        user.save()
        for role_id in input.role_ids:
            role = Role.objects.filter(id=role_id).first()
            if role is not None:
                UserRole.objects.create(user=user, role=role)
        return Success(id=str(user.id), message="created")


class AssignRole(graphene.Mutation):
    class Arguments:
        user_id = graphene.ID(required=True)
        role_id = graphene.ID(required=True)

    Output = MutationResult

    def mutate(self, info, user_id, role_id):
        from apps.common.permissions import has_permission
        from apps.common.graphql_types import PermissionDenied
        actor = getattr(info.context, "user", None)
        if not has_permission(actor, "accounts.manage"):
            return PermissionDenied(code="permission_denied", message="Missing permission: accounts.manage")
        user = AgencyUser.objects.filter(id=user_id).first()
        role = Role.objects.filter(id=role_id).first()
        if user is None:
            return _validation("user_id", "User not found")
        if role is None:
            return _validation("role_id", "Role not found")
        UserRole.objects.get_or_create(user=user, role=role)
        return Success(id=str(user.id), message="assigned")


class RevokeRole(graphene.Mutation):
    class Arguments:
        user_id = graphene.ID(required=True)
        role_id = graphene.ID(required=True)

    Output = MutationResult

    def mutate(self, info, user_id, role_id):
        from apps.common.permissions import has_permission
        from apps.common.graphql_types import PermissionDenied
        actor = getattr(info.context, "user", None)
        if not has_permission(actor, "accounts.manage"):
            return PermissionDenied(code="permission_denied", message="Missing permission: accounts.manage")
        user = AgencyUser.objects.filter(id=user_id).first()
        role = Role.objects.filter(id=role_id).first()
        if user is None or role is None:
            return _validation("non_field", "User or role not found")
        UserRole.objects.filter(user=user, role=role).delete()
        return Success(id=str(user.id), message="revoked")


class DeactivateAgencyUser(graphene.Mutation):
    class Arguments:
        user_id = graphene.ID(required=True)

    Output = MutationResult

    def mutate(self, info, user_id):
        from apps.common.permissions import has_permission
        from apps.common.graphql_types import PermissionDenied
        actor = getattr(info.context, "user", None)
        if not has_permission(actor, "accounts.manage"):
            return PermissionDenied(code="permission_denied", message="Missing permission: accounts.manage")
        if actor is not None and str(actor.id) == str(user_id):
            return _validation("user_id", "Cannot deactivate yourself")
        user = AgencyUser.objects.filter(id=user_id).first()
        if user is None:
            return _validation("user_id", "User not found")
        user.is_active = False
        user.save()
        return Success(id=str(user.id), message="deactivated")


class Query(graphene.ObjectType):
    me = graphene.Field(AgencyUserType)
    agency_users = graphene.List(graphene.NonNull(AgencyUserType), search=graphene.String(), required=True)
    roles_list = graphene.List(graphene.NonNull(RoleType), required=True)

    def resolve_me(self, info):
        user = getattr(info.context, "user", None)
        if user and getattr(user, "is_authenticated", False):
            return user
        return None

    def resolve_agency_users(self, info, search=None):
        from apps.common.permissions import has_permission
        actor = getattr(info.context, "user", None)
        if not has_permission(actor, "accounts.read"):
            return []
        qs = AgencyUser.objects.filter(is_active=True)
        if search:
            qs = qs.filter(email__icontains=search) | qs.filter(first_name__icontains=search) | qs.filter(last_name__icontains=search)
        return list(qs.order_by("email"))

    def resolve_roles_list(self, info):
        from apps.common.permissions import has_permission
        actor = getattr(info.context, "user", None)
        if not has_permission(actor, "accounts.read"):
            return []
        return list(Role.objects.all().order_by("name"))


class Mutation(graphene.ObjectType):
    login = Login.Field()
    refresh_token = RefreshTokenMutation.Field()
    logout = Logout.Field()
    create_agency_user = CreateAgencyUser.Field()
    assign_role = AssignRole.Field()
    revoke_role = RevokeRole.Field()
    deactivate_agency_user = DeactivateAgencyUser.Field()
