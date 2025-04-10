import factory
import faker
from faker.providers import internet

fake = faker.Faker()
fake.add_provider(internet)


class ShortUrlFactory(factory.django.DjangoModelFactory):
    full_url = fake.uri()

    class Meta:
        model = "baseapp_url_shortening.ShortUrl"
