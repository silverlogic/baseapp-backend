import factory


class ModeFactory(factory.django.DjangoModelFactory):
    name = factory.Faker("bs")

    class Meta:
        model = "testapp.Mode"
