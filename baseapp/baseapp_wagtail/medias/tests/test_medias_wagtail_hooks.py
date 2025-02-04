from django.core.files.base import ContentFile
from django.test import TestCase
from wagtail.images.formats import get_image_format
from wagtail.rich_text import expand_db_html

import baseapp_wagtail.medias.tests.factories as f


class RichTextDocumentLinkHandlerTests(TestCase):
    def setUp(self):
        self.document = f.DocumentFactory()
        self.document.file.save(
            "sample_name.pdf",
            ContentFile("A boring example document"),
        )

    def test_custom_document_link_handler(self):
        html = f'<a id="{self.document.id}" linktype="document">foo</a>'
        result = expand_db_html(html)
        self.assertIn('target="_blank"', result)

    def test_documents_with_full_url(self):
        html = f'<a id="{self.document.id}" linktype="document">foo</a>'
        result = expand_db_html(html)
        self.assertIn(".pdf", result)
        self.assertIn("sample_name", result)


class RichTextImageFormatsTests(TestCase):
    def setUp(self):
        self.image = f.ImageFactory()

    def test_full_width_image_format(self):
        result = get_image_format("fullwidth").image_to_editor_html(self.image, "test alt text")
        self.assertIn("width-1472", result)
        self.assertIn("richtext-image full-width", result)
        self.assertIn("test alt text", result)

    def test_original_size_image_format(self):
        result = get_image_format("originalsize").image_to_editor_html(self.image, "test alt text")
        self.assertIn("richtext-image original-size", result)
        self.assertIn("test alt text", result)
