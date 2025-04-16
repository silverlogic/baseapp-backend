import factory
import swapper

ContentPost = swapper.load_model(
    "baseapp_content_feed", "ContentPost", required=False, require_ready=False
)


class AbstractContentPostFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory("baseapp_core.tests.factories.UserFactory")
    content = factory.Faker("text")

    class Meta:
        abstract = True


class ContentPostFactory(AbstractContentPostFactory):
    class Meta:
        model = ContentPost
