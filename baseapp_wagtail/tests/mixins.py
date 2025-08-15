import urllib.parse
from typing import Type

from django.test import TestCase, override_settings
from django.urls import reverse
from wagtail.models import Page, Site
from wagtail.test.utils import WagtailPageTestCase, WagtailTestUtils

import baseapp_wagtail.medias.tests.factories as medias_factories
from baseapp_core.tests.factories import UserFactory
from baseapp_wagtail.tests.factories.wagtail_factories import LocaleFactory
from baseapp_wagtail.tests.models import PageForTests


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"])
class WagtailBasicMixin(WagtailPageTestCase, WagtailTestUtils, TestCase):
    pass


class TestPageContextMixin(WagtailBasicMixin):
    page_model: Type[Page] = PageForTests
    root_page: PageForTests
    page: PageForTests

    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory()
        root_page = Page.get_first_root_node()
        if not root_page:
            LocaleFactory(language_code="en")
            root_page = cls.page_model(
                title="Root",
                slug="root",
                depth=1,
                path="0001",
            )
            root_page.save()
        cls.root_page = root_page
        cls.site, _ = Site.objects.get_or_create(
            is_default_site=True,
            defaults={
                "hostname": "localhost",
                "root_page": root_page,
                "is_default_site": True,
                "site_name": "localhost",
            },
        )
        cls.page = cls.page_model(
            title="My Page",
            slug="mypage",
            depth=cls.site.root_page.depth + 1,
            path=f"{cls.site.root_page.path}0001",
        )
        cls.site.root_page.add_child(instance=cls.page)

    def _reload_the_page(self):
        self.page = self.page_model.objects.get(id=self.page.id)

    def _get_edit_page(self, page):
        response = self.client.get(reverse("wagtailadmin_pages:edit", args=[page.id]))
        return response

    def _get_featured_image_raw_data(self):
        image = medias_factories.ImageFactory()
        return {
            "featured_image-count": "1",
            "featured_image-0-deleted": "",
            "featured_image-0-order": "0",
            "featured_image-0-type": "featured_image",
            "featured_image-0-id": "random-id",
            "featured_image-0-value-image": image.id,
            "featured_image-0-value-alt_text": "",
            "featured_image-0-value-attribution": "",
            "featured_image-0-value-caption": "",
        }


class WagtailApiMixin:
    view_name = ""
    url_kwargs = None

    def reverse(self, view_name=None, query_params=None, **kwargs):
        version = "wagtailapi"

        if self.url_kwargs is not None:
            kwargs.setdefault("kwargs", self.url_kwargs)

        if not view_name:
            view_name = self.view_name

        url = reverse("{}:{}".format(version, view_name), **kwargs)

        if query_params:
            url += "?" + urllib.parse.urlencode(
                query_params, doseq=True, quote_via=urllib.parse.quote
            )

        return url
