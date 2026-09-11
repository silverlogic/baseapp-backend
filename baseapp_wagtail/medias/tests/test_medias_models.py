from django.test import TestCase, override_settings

import baseapp_wagtail.medias.tests.factories as f
from baseapp_wagtail.medias.models import CustomImage


class TestCustomImageModel(TestCase):
    def setUp(self) -> None:
        self.image = f.ImageFactory(alt_text="")

    def test_image_without_custom_fields(self) -> None:
        self.assertEqual(self.image.alt_text, "")

    def test_alt_text_field(self) -> None:
        self.image.alt_text = "Test alt text"
        self.image.save()

        r_img = CustomImage.objects.get(id=self.image.id)
        self.assertEqual(r_img.alt_text, "Test alt text")

    def test_default_alt_text(self) -> None:
        self.image.alt_text = "Test alt text"
        self.image.save()

        self.assertEqual(self.image.default_alt_text, "Test alt text")

    def test_default_alt_text_without_alt_text(self) -> None:
        self.assertEqual(self.image.default_alt_text, "")


@override_settings(WAGTAILADMIN_BASE_URL="http://example.com/")  # NOSONAR
class TestCustomDocumentModel(TestCase):
    def test_file_extension_field(self) -> None:
        document = f.DocumentFactory()
        self.assertTrue(document.url.startswith("http://example.com/"))  # NOSONAR
