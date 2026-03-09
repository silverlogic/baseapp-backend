import factory

from testproject.testapp.models import (
    DummyLegacyModel,
    DummyLegacyWithPkModel,
    DummyPublicIdModel,
)


class DummyPublicIdModelFactory(factory.django.DjangoModelFactory):
    name = factory.Faker("name")

    class Meta:
        model = DummyPublicIdModel


class DummyLegacyWithPkModelFactory(factory.django.DjangoModelFactory):
    name = factory.Faker("name")

    class Meta:
        model = DummyLegacyWithPkModel


class DummyLegacyModelFactory(factory.django.DjangoModelFactory):
    name = factory.Faker("name")

    class Meta:
        model = DummyLegacyModel
