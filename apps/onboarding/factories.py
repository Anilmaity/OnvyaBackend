import factory

from apps.onboarding.models import Application
from apps.drivers.factories import DriverFactory


class ApplicationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Application

    agency = factory.SelfAttribute("driver.agency")
    driver = factory.SubFactory(DriverFactory)
    state = Application.State.IN_PROGRESS
