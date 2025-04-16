import factory


class LocaleFactory(factory.django.DjangoModelFactory):
    language_code = "en"

    class Meta:
        model = "wagtailcore.Locale"


class GroupFactory(factory.django.DjangoModelFactory):
    name = factory.Faker("word")

    class Meta:
        model = "auth.Group"


class PageFactory(factory.django.DjangoModelFactory):
    title = factory.Faker("word")
    slug = factory.Faker("slug")
    depth = 1
    path = factory.Sequence(lambda n: f"000{n:04d}")

    class Meta:
        model = "wagtailcore.Page"
