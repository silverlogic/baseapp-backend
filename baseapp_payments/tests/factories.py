import factory
import swapper

from baseapp_profiles.tests.factories import ProfileFactory


class UserFactory(factory.django.DjangoModelFactory):
    email = factory.Faker("email")
    password = factory.PostGenerationMethodCall("set_password", "default")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")

    class Meta:
        model = "users.User"


class CustomerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = swapper.load_model("baseapp_payments", "Customer")

    entity = factory.SubFactory(ProfileFactory)
    remote_customer_id = factory.Faker("uuid4")


class SubscriptionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = swapper.load_model("baseapp_payments", "Subscription")

    customer = factory.SubFactory(CustomerFactory)
    remote_subscription_id = factory.Faker("uuid4")
