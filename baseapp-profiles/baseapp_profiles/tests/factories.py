import factory
import swapper

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")


class ProfileFactory(factory.django.DjangoModelFactory):
    owner = factory.SubFactory("baseapp_core.tests.factories.UserFactory")

    class Meta:
        model = Profile


class ProfileUserRoleFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory("baseapp_core.tests.factories.UserFactory")
    profile = factory.SubFactory(ProfileFactory)

    class Meta:
        model = ProfileUserRole
