from django.core.exceptions import ValidationError

from baseapp_pages.tests.factories import URLPathFactory
from baseapp_wagtail.tests.mixins import TestPageContextMixin


class URLPathPageModelsTests(TestPageContextMixin):
    def test_urlpath_slug_validation_with_existing_urlpath(self):
        URLPathFactory(path="/mypage")
        self.page.slug = "mypage"
        with self.assertRaises(ValidationError):
            self.page.save()

    def test_urlpath_slug_validation_with_existing_urlpath_for_same_page(self):
        URLPathFactory(path="/mypage", target=self.page)
        self.page.slug = "mypage"
        self.page.save()

    def test_urlpath_slug_validation_without_existing_urlpath(self):
        self.page.slug = "mypage"
        self.page.save()
