import factory
import swapper

Profile = swapper.load_model("baseapp_profiles", "Profile")


class ProfileFactory(factory.django.DjangoModelFactory):
    owner = factory.SubFactory("baseapp_core.tests.factories.UserFactory")

    class Meta:
        model = Profile
