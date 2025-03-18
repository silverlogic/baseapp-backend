from django.urls import reverse
from rest_framework import status

import baseapp_wagtail.medias.tests.factories as media_factory
from baseapp_wagtail.tests.mixins import StandardPageContextMixin
from baseapp_wagtail.tests.models import PageForTests


class PagesAPITests(StandardPageContextMixin):
    def test_page_url_path(self):
        new_page = PageForTests(
            title="My Page Child",
            slug="mypage-child",
        )
        self.page.add_child(instance=new_page)
        new_page.save_revision().publish()
        response = self.client.get(
            reverse("baseappwagtailapi_base:pages:detail", args=[new_page.id]),
            {"type": "tests.PageForTests", "fields": "*"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["meta"]["url_path"], "/mypage/mypage-child/")

    def test_path_endpoint(self):
        response = self.client.get(
            reverse("baseappwagtailapi_base:pages:path"), {"html_path": "/mypage/"}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["id"], self.page.id)

    def test_path_endpoint_with_similar_paths(self):
        new_page = PageForTests(
            title="My Page",
            slug="mypage",
        )
        self.page.add_child(instance=new_page)

        new_page.save_revision().publish()

        response = self.client.get(
            reverse("baseappwagtailapi_base:pages:path"), {"html_path": "/mypage/"}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["id"], self.page.id)


class DefaultPageModelAPISerializerTests(StandardPageContextMixin):
    def setUp(self):
        super().setUp()
        self.new_page = PageForTests(
            title="My Standard Page",
            slug="my-standard-page",
            live=False,
        )
        self.page.add_child(instance=self.new_page)

    def test_page_featured_image(self):
        image = media_factory.ImageFactory()
        self.page.featured_image.extend([("featured_image", {"image": image})])
        self.page.save()
        self.page.save_revision().publish()

        response = self.client.get(
            reverse("baseappwagtailapi_base:pages:detail", args=[self.page.id]),
            {"type": "tests.PageForTests", "fields": "*"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["featured_image"]["image"]["id"], image.id)

    def test_page_ancestors(self):
        self.new_page.save_revision().publish()
        response = self.client.get(
            reverse("baseappwagtailapi_base:pages:detail", args=[self.new_page.id]),
            {"type": "tests.PageForTests", "fields": "*"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()["meta"]["ancestors"]), 2)
        self.assertEqual(response.json()["meta"]["ancestors"][0]["id"], self.page.get_parent().id)
        self.assertEqual(response.json()["meta"]["ancestors"][1]["id"], self.page.id)
        self.assertIsNotNone(response.json()["meta"]["ancestors"][0]["url_path"])
        self.assertIsNotNone(response.json()["meta"]["ancestors"][0]["type"])
        self.assertIsNotNone(response.json()["meta"]["ancestors"][0]["locale"])

    def test_page_with_unpublished_ancestor(self):
        self.page.live = False
        self.page.save()
        self.new_page.save_revision().publish()
        response = self.client.get(
            reverse("baseappwagtailapi_base:pages:detail", args=[self.new_page.id]),
            {"type": "tests.PageForTests", "fields": "*"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()["meta"]["ancestors"]), 1)
        self.assertEqual(response.json()["meta"]["ancestors"][0]["id"], self.page.get_parent().id)

    def test_path_endpoint_with_locale_prefix(self):
        response = self.client.get(
            reverse("baseappwagtailapi_base:pages:path"), {"html_path": "/es/mypage/"}
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
