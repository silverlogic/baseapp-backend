from django.test import TestCase

import baseapp_wagtail.medias.tests.factories as f
from baseapp_wagtail.medias.models import CustomImage


class TestCustomImageModel(TestCase):
    def setUp(self):
        self.image = f.ImageFactory(alt_text="")

    def test_image_without_custom_fields(self):
        self.assertEqual(self.image.alt_text, "")

    def test_alt_text_field(self):
        self.image.alt_text = "Test alt text"
        self.image.save()

        r_img = CustomImage.objects.get(id=self.image.id)
        self.assertEqual(r_img.alt_text, "Test alt text")

    def test_default_alt_text(self):
        self.image.alt_text = "Test alt text"
        self.image.save()

        self.assertEqual(self.image.default_alt_text, "Test alt text")

    def test_default_alt_text_without_alt_text(self):
        self.assertEqual(self.image.default_alt_text, "")
