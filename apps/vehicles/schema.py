from graphene_django import DjangoObjectType

from apps.vehicles.models import Vehicle


class VehicleType(DjangoObjectType):
    class Meta:
        model = Vehicle
        fields = ("id", "registration", "make", "model", "year", "colour")
