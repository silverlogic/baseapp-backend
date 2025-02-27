from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from wagtail.test.utils.form_data import nested_form_data, streamfield

import baseapp_wagtail.medias.tests.factories as media_factory
from baseapp_wagtail.tests.mixins import StandardPageContextMixin
from baseapp_wagtail.tests.models import PageForTests


class BasicPageTestsMixin(StandardPageContextMixin):
    model = None

    @override_settings(FRONT_HEADLESS_URL="testserver")
    def test_get_url_with_site(self):
        if not self.model:
            return
        page = self.model(
            title="My Basic Page",
            slug="mybasicpage",
        )
        self.site.root_page.add_child(instance=page)
        self.assertEqual(page.headless_url, f"testserver/{page.slug}/")

    class Meta:
        abstract = True


class StandardPageTests(BasicPageTestsMixin):
    model = PageForTests
    page_type = "tests.PageForTests"

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.standard_page = cls.page
        cls.page = cls.model(
            title="My Standard Page",
            slug="mystandardpage",
        )
        cls.standard_page.add_child(instance=cls.page)

    def setUp(self):
        self.login()

    def test_default_route(self):
        self.assertPageIsRoutable(self.page)

    def test_default_route_rendering(self):
        self.assertPageIsRenderable(self.page)

    def test_can_create_standard_page(self):
        image = media_factory.ImageFactory()
        self.assertCanCreate(
            self.site.root_page,
            self.model,
            nested_form_data(
                {
                    "title": "About us",
                    "featured_image": streamfield([("featured_image", {"image": image.id})]),
                    "hero_settings-count": "0",
                    "body": streamfield(
                        [
                            ("text", "Lorem ipsum dolor sit amet"),
                        ]
                    ),
                }
            ),
        )

    def test_api_fields(self):
        self.page.featured_image.extend(
            [
                (
                    "featured_image",
                    {
                        "image": media_factory.ImageFactory(),
                    },
                )
            ]
        )
        self.page.save()
        self.page.save_revision().publish()
        response = self.client.get(
            reverse("baseappwagtailapi_base:pages:detail", args=[self.page.id]),
            {"type": self.page_type, "fields": "*"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["meta"]["type"], self.page_type)
        self.assertIsNotNone(response.json()["featured_image"])
        self.assertIsNotNone(response.json()["body"])
