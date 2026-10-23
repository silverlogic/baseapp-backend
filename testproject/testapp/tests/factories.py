import factory

from testproject.testapp.models import (
    DummyLegacyModel,
    DummyLegacyWithPkModel,
    DummyPublicIdChildModel,
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


class DummyPublicIdChildModelFactory(factory.django.DjangoModelFactory):
    name = factory.Faker("name")
    parent = factory.SubFactory(DummyPublicIdModelFactory)

    class Meta:
        model = DummyPublicIdChildModel
