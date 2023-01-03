import factory


class UserFactory(factory.django.DjangoModelFactory):
    email = factory.Faker("email")
    password = factory.PostGenerationMethodCall("set_password", "default")

    class Meta:
        model = "users.User"

    @factory.post_generation
    def permission_groups(self, create, extracted, **kwargs):
        if create and extracted:
            self.permission_groups.add(*extracted)


class PasswordValidationFactory(factory.django.DjangoModelFactory):
    name = "apps.users.password_validators.MustContainSpecialCharacterValidator"

    class Meta:
        model = "users.PasswordValidation"


class TokenFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory(UserFactory)

    class Meta:
        model = "authtoken.Token"
