from rest_framework import status
from wagtail.models import Locale

from baseapp_wagtail.base.urlpath.urlpath_sync import WagtailURLPathSync
from baseapp_wagtail.tests.mixins import TestPageContextMixin
from baseapp_wagtail.tests.utils.graphql_helpers import GraphqlHelper
from testproject.base.models import StandardPage


class WagtailURLPathObjectTypeTests(GraphqlHelper, TestPageContextMixin):
    def setUp(self):
        super().setUp()
        self.page.save_revision().publish()
        WagtailURLPathSync(self.page).create_urlpath()
        self.url_path = self.page.pages_url_path

    def test_urlpath_query_returns_wagtail_page_data(self):
        response = self.query(
            """
            query Page($path: String!) {
                urlPath(path: $path) {
                    path
                    target {
                        __typename
                        ... on WagtailPage {
                            data {
                                id
                                title
                                ... on PageForTests {
                                    body {
                                        ... on RichTextBlock {
                                            value
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            """,
            variables={"path": self.url_path.path},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = response.json()

        self.assertIsNotNone(content["data"]["urlPath"])
        self.assertEqual(content["data"]["urlPath"]["path"], self.url_path.path)

        target = content["data"]["urlPath"]["target"]
        self.assertEqual(target["__typename"], "WagtailPage")

        data = target["data"]
        self.assertEqual(data["id"], str(self.page.id))
        self.assertEqual(data["title"], self.page.title)

    def test_urlpath_query_with_metadata(self):
        response = self.query(
            """
            query Page($path: String!) {
                urlPath(path: $path) {
                    target {
                        ... on WagtailPage {
                            data {
                                ... on PageForTests {
                                    metadata {
                                        metaTitle
                                        metaDescription
                                        metaOgType
                                    }
                                }
                            }
                        }
                    }
                }
            }
            """,
            variables={"path": self.url_path.path},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = response.json()

        data = content["data"]["urlPath"]["target"]["data"]
        metadata = data["metadata"]
        self.assertIsNotNone(metadata)
        self.assertEqual(metadata["metaTitle"], self.page.title)
        self.assertEqual(metadata["metaOgType"], "article")

    def test_urlpath_query_with_standard_page(self):
        standard_page = StandardPage(
            title="Standard Test Page",
            slug="standard-test-page",
            path=f"{self.site.root_page.path}0002",
            depth=self.site.root_page.depth + 1,
        )
        self.site.root_page.add_child(instance=standard_page)
        standard_page.save_revision().publish()
        WagtailURLPathSync(standard_page).create_urlpath()
        standard_url_path = standard_page.pages_url_path

        response = self.query(
            """
            query Page($path: String!) {
                urlPath(path: $path) {
                    path
                    target {
                        __typename
                        ... on WagtailPage {
                            data {
                                id
                                title
                                ... on StandardPage {
                                    path
                                }
                            }
                        }
                    }
                }
            }
            """,
            variables={"path": standard_url_path.path},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = response.json()

        self.assertIsNotNone(content["data"]["urlPath"])
        target = content["data"]["urlPath"]["target"]
        self.assertEqual(target["__typename"], "WagtailPage")

        data = target["data"]
        self.assertEqual(data["id"], str(standard_page.id))
        self.assertEqual(data["title"], standard_page.title)

    def test_urlpath_query_with_comments_interface(self):
        standard_page = StandardPage(
            title="Standard Test Page",
            slug="standard-test-page",
            path=f"{self.site.root_page.path}0002",
            depth=self.site.root_page.depth + 1,
        )
        self.site.root_page.add_child(instance=standard_page)
        standard_page.save_revision().publish()
        WagtailURLPathSync(standard_page).create_urlpath()
        standard_url_path = standard_page.pages_url_path

        response = self.query(
            """
            query Page($path: String!) {
                urlPath(path: $path) {
                    target {
                        ... on WagtailPage {
                            data {
                                ... on StandardPage {
                                    commentsCount {
                                        total
                                    }
                                }
                            }
                        }
                    }
                }
            }
            """,
            variables={"path": standard_url_path.path},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json()["data"]["urlPath"]["target"]["data"]["commentsCount"]["total"], 0
        )

    def test_urlpath_query_inactive_path(self):
        self.page.update_url_path(path="/inactive-page", language="en", is_active=False)

        response = self.query(
            """
            query Page($path: String!) {
                urlPath(path: $path) {
                    path
                    target {
                        ... on WagtailPage {
                            data {
                                id
                                title
                            }
                        }
                    }
                }
            }
            """,
            variables={"path": "/inactive-page"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.json()["data"]["urlPath"])

    def test_urlpath_query_nonexistent_path(self):
        response = self.query(
            """
            query Page($path: String!) {
                urlPath(path: $path) {
                    path
                    target {
                        ... on WagtailPage {
                            data {
                                id
                                title
                            }
                        }
                    }
                }
            }
            """,
            variables={"path": "/nonexistent-page"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = response.json()

        self.assertIsNone(content["data"]["urlPath"])

    def test_urlpath_query_with_language_specific_path(self):
        standard_page = StandardPage(
            title="Standard Test Page",
            slug="standard-test-page",
            path=f"{self.site.root_page.path}0002",
            depth=self.site.root_page.depth + 1,
            locale=Locale.objects.get_or_create(language_code="pt")[0],
        )
        self.site.root_page.add_child(instance=standard_page)
        standard_page.save_revision().publish()
        WagtailURLPathSync(standard_page).create_urlpath()
        pt_url_path = standard_page.pages_url_path

        response = self.query(
            """
            query Page($path: String!) {
                urlPath(path: $path) {
                    path
                    target {
                        ... on WagtailPage {
                            data {
                                id
                                title
                            }
                        }
                    }
                }
            }
            """,
            variables={"path": pt_url_path.path},
            headers={"HTTP_ACCEPT_LANGUAGE": "pt"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = response.json()

        self.assertIsNotNone(content["data"]["urlPath"])
        self.assertEqual(content["data"]["urlPath"]["path"], pt_url_path.path)
