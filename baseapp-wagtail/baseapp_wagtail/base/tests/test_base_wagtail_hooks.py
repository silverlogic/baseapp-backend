from django.test import TestCase
from wagtail.rich_text import expand_db_html
from wagtail.rich_text.feature_registry import FeatureRegistry


class RichTextFeaturesRegistryTests(TestCase):
    def test_register_rich_text_features_hook(self):
        feat_registry = FeatureRegistry()
        features = feat_registry.get_default_features()
        self.assertIn("blockquote", features)

    def test_external_link_handler(self):
        html = '<a href="example.com" linktype="external">foo</a>'
        result = expand_db_html(html)
        self.assertIn('target="_blank"', result)

    def test_email_link_handler(self):
        html = '<a href="mailto:test@example.org" linktype="email">foo</a>'
        result = expand_db_html(html)
        self.assertIn('class="notranslate"', result)
