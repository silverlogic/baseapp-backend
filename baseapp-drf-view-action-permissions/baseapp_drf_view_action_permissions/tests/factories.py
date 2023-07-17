import factory
from django.contrib.auth.models import Group

from drf_view_action_permissions.models import IpRestriction
from testproject.testapp.models import TestModel


class UserFactory(factory.DjangoModelFactory):
    class Meta:
        model = "testapp.User"

    @factory.post_generation
    def groups(self, create, extracted, **kwargs):
        if create and extracted:
            self.groups.add(*extracted)

    @factory.post_generation
    def exclude_permissions(self, create, extracted, **kwargs):
        if create and extracted:
            self.exclude_permissions.add(*extracted)


class GroupFactory(factory.DjangoModelFactory):
    name = factory.Faker("company")

    class Meta:
        model = Group

    @factory.post_generation
    def permissions(self, create, extracted, **kwargs):
        if create and extracted:
            self.permissions.add(*extracted)


class RoleFactory(factory.DjangoModelFactory):
    name = factory.Faker("job")

    class Meta:
        model = "baseapp_drf_view_action_permissions.Role"

    @factory.post_generation
    def permissions(self, create, extracted, **kwargs):
        if create and extracted:
            self.permissions.add(*extracted)

    @factory.post_generation
    def groups(self, create, extracted, **kwargs):
        if create and extracted:
            self.groups.add(*extracted)

    @factory.post_generation
    def exclude_permissions(self, create, extracted, **kwargs):
        if create and extracted:
            self.exclude_permissions.add(*extracted)


class TestModelFactory(factory.DjangoModelFactory):
    title = factory.Faker("name")

    class Meta:
        model = TestModel


class IpRestrictionFactory(factory.DjangoModelFactory):
    ip_address = factory.Faker("ipv4")

    @factory.post_generation
    def unrestricted_roles(self, create, extracted, **kwargs):
        if create and extracted:
            self.unrestricted_roles.add(*extracted)

    class Meta:
        model = IpRestriction
