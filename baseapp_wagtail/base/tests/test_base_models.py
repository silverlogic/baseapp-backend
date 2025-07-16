from rest_framework import status
from wagtail.test.utils.form_data import nested_form_data, streamfield

import baseapp_wagtail.medias.tests.factories as media_factory
from baseapp_wagtail.tests.mixins import TestPageContextMixin
from baseapp_wagtail.tests.models import PageForTests
from baseapp_wagtail.tests.utils.graphql_helpers import GraphqlHelper


class PageForTestsTests(GraphqlHelper, TestPageContextMixin):
    model = PageForTests
    page_type = "PageForTests"

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.standard_page = cls.page
        cls.page = cls.model(
            title="My Page",
            slug="mypage",
            path=f"{cls.site.root_page.path}0001",
            depth=cls.site.root_page.depth + 1,
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
        response = self.query(
            """
query Page($id: ID!) {
    page(id: $id) {
        id
        title
        pageType
        ... on PageForTests {
            body {
                id
            }
        }
    }
}
""",
            variables={"id": self.page.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["data"]["page"]["pageType"], self.page_type)
        self.assertIsNotNone(response.json()["data"]["page"]["body"])
