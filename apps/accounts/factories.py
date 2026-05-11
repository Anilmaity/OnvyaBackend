import factory

from apps.agencies.models import Agency
from apps.accounts.models import AgencyUser


class AgencyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Agency

    name = factory.Sequence(lambda n: f"Agency {n}")
    slug = factory.Sequence(lambda n: f"agency-{n}")


class AgencyUserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AgencyUser
        django_get_or_create = ("email",)

    agency = factory.SubFactory(AgencyFactory)
    email = factory.Sequence(lambda n: f"user{n}@test")
    password = "demo1234"
    is_active = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop("password", "demo1234")
        user = model_class(**kwargs)
        user.set_password(password)
        user.save()
        return user
