import graphene
from graphene_django import DjangoObjectType

from apps.agencies.models import Agency, Depot
from apps.common.permissions import permission_required


class AgencyType(DjangoObjectType):
    class Meta:
        model = Agency
        fields = ("id", "name", "slug", "timezone", "primary_color", "is_active")


class DepotType(DjangoObjectType):
    class Meta:
        model = Depot
        fields = ("id", "name", "address", "is_active", "agency")


class Query(graphene.ObjectType):
    my_agency = graphene.Field(AgencyType)
    depots = graphene.List(graphene.NonNull(DepotType), required=True)

    def resolve_my_agency(self, info):
        agency = getattr(info.context, "current_agency", None)
        return agency

    @permission_required("agencies.read")
    def resolve_depots(self, info):
        return list(Depot.objects.filter(is_active=True))
