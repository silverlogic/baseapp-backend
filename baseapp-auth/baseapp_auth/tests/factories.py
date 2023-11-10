import baseapp_auth.tests.helpers as h
import factory

UserFactory = h.get_user_factory()


class PasswordValidationFactory(factory.django.DjangoModelFactory):
    name = "baseapp_auth.password_validators.MustContainSpecialCharacterValidator"

    class Meta:
        model = "baseapp_auth.PasswordValidation"


class TokenFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory(UserFactory)

    class Meta:
        model = "authtoken.Token"
