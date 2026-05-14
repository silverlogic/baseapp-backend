import factory
import swapper


class UserFactory(factory.django.DjangoModelFactory):
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    password = factory.PostGenerationMethodCall("set_password", "default")  # NOSONAR
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")

    class Meta:
        model = "users.User"


class CustomerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = swapper.load_model("baseapp_payments", "Customer")

    entity = factory.SubFactory(UserFactory)
    remote_customer_id = factory.Faker("uuid4")
