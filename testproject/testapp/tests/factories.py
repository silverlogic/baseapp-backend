import factory

from testproject.testapp.models import DummyLegacyModel, DummyPublicIdModel


class DummyPublicIdModelFactory(factory.django.DjangoModelFactory):
    name = factory.Faker("name")

    class Meta:
        model = DummyPublicIdModel


class DummyLegacyModelFactory(factory.django.DjangoModelFactory):
    name = factory.Faker("name")

    class Meta:
        model = DummyLegacyModel
