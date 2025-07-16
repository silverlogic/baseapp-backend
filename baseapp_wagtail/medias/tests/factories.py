import factory
from wagtail.documents import get_document_model
from wagtail.images import get_image_model
from wagtail.models import Collection

from baseapp_wagtail.tests.utils.media_helper import (
    get_test_document_file,
    get_test_image_file,
)


class CollectionFactory(factory.django.DjangoModelFactory):
    name = factory.Faker("name")
    depth = 1

    class Meta:
        model = Collection


class ImageFactory(factory.django.DjangoModelFactory):
    title = "Test image"
    file = get_test_image_file()
    collection = factory.SubFactory(CollectionFactory)

    class Meta:
        model = get_image_model()


class DocumentFactory(factory.django.DjangoModelFactory):
    title = "Test document"
    file = get_test_document_file()
    collection = factory.SubFactory(CollectionFactory)

    class Meta:
        model = get_document_model()
