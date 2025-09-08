import factory

from testproject.testapp.models import DummyPublicIdModel


class DummyPublicIdModelFactory(factory.django.DjangoModelFactory):
    name = factory.Faker("name")

    class Meta:
        model = DummyPublicIdModel
