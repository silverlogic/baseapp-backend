import factory

from .utils import get_test_document_file, get_test_image_file


class CustomImageFactory(factory.django.DjangoModelFactory):
    alt_text = "Test alt text"
    attribution = "Test image attribution"
    caption = "Test image caption"
    title = "Test image"
    file = get_test_image_file()

    class Meta:
        model = "medias.CustomImage"


class CustomDocumentFactory(factory.django.DjangoModelFactory):
    title = "Test document"
    file = get_test_document_file()

    class Meta:
        model = "medias.CustomDocument"
