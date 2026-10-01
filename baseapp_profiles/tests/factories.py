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
    # The model default is INACTIVE because an invited member starts out PENDING and is
    # only activated on acceptance. A membership built straight from this factory stands
    # for a member who is already on board, so it defaults to ACTIVE — anything else
    # grants no access at all. Pass `status=` explicitly to test the other states.
    status = ProfileUserRole.ProfileRoleStatus.ACTIVE

    class Meta:
        model = ProfileUserRole
