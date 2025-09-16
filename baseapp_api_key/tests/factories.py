import factory

import baseapp_auth.tests.helpers as h

UserFactory = h.get_user_factory()
from uuid import uuid4


class APIKeyFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory(UserFactory)
    name = factory.Sequence(lambda _: f"API-Key-{uuid4()}")
    encrypted_api_key = factory.LazyAttribute(lambda _: bytes())

    class Meta:
        model = "baseapp_api_key.APIKey"

    @factory.post_generation
    def default_unencrypted_api_key(self, create, extracted, **kwargs):
        if create:
            unencrypted_api_key = self.__class__.objects.generate_unencrypted_api_key()
            self.encrypted_api_key = self.__class__.objects.encrypt(
                unencrypted_value=unencrypted_api_key
            )
            self.save(update_fields=["encrypted_api_key"])
