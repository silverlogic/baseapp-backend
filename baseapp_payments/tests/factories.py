import factory
import swapper

from baseapp_core.tests.factories import UserFactory


class CustomerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = swapper.load_model("baseapp_payments", "Customer")

    entity = factory.SubFactory(UserFactory)
    remote_customer_id = factory.Faker("uuid4")
