import factory
import swapper

Organization = swapper.load_model("baseapp_organizations", "Organization")


class OrganizationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Organization
