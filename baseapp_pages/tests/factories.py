import factory
import swapper
from django.contrib.contenttypes.models import ContentType

from baseapp_pages.models import Metadata, URLPath

Page = swapper.load_model("baseapp_pages", "Page")


class PageFactory(factory.django.DjangoModelFactory):
    status = Page.PageStatus.PUBLISHED

    class Meta:
        model = Page


class URLPathFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = URLPath


class MetadataFactory(factory.django.DjangoModelFactory):
    meta_title = factory.Faker("sentence", nb_words=4)
    meta_description = factory.Faker("text", max_nb_chars=160)
    meta_og_type = "website"

    # Generic foreign key fields (correct field names)
    target_content_type = factory.LazyFunction(lambda: ContentType.objects.get_for_model(Page))
    target_object_id = factory.Sequence(lambda n: n + 1)

    class Meta:
        model = Metadata
