import factory
from wagtail.contrib.redirects.models import Redirect


class RedirectFactory(factory.django.DjangoModelFactory):
    old_path = factory.Faker("url")
    is_permanent = factory.Faker("boolean")
    redirect_link = factory.Faker("url")

    class Meta:
        model = Redirect
