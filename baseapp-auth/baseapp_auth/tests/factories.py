import factory


class UserFactory(factory.django.DjangoModelFactory):
    email = factory.Faker("email")
    password = factory.PostGenerationMethodCall("set_password", "default")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")

    class Meta:
        model = "testapp.User"


class PasswordValidationFactory(factory.django.DjangoModelFactory):
    name = "baseapp_auth.password_validators.MustContainSpecialCharacterValidator"

    class Meta:
        model = "baseapp_auth.PasswordValidation"


class TokenFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory(UserFactory)

    class Meta:
        model = "authtoken.Token"
