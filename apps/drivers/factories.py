import factory

from apps.drivers.models import Driver
from apps.accounts.factories import AgencyFactory


class DriverFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Driver

    agency = factory.SubFactory(AgencyFactory)
    first_name = factory.Sequence(lambda n: f"First{n}")
    last_name = factory.Sequence(lambda n: f"Last{n}")
    email = factory.Sequence(lambda n: f"driver{n}@a.test")
    status = Driver.Status.PENDING
