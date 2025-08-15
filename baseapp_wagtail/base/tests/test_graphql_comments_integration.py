from rest_framework import status

from baseapp_comments.tests.factories import CommentFactory
from baseapp_wagtail.tests.mixins import TestPageContextMixin
from baseapp_wagtail.tests.utils.graphql_helpers import GraphqlHelper
from testproject.base.models import StandardPage


class WagtailCommentsIntegrationTests(GraphqlHelper, TestPageContextMixin):
    page_model = StandardPage

    def setUp(self):
        super().setUp()
        self.page.save_revision().publish()

    def test_wagtail_page_has_comments_interface(self):
        response = self.query(
            """
            query Page($id: ID!) {
                page(id: $id) {
                    id
                    title
                    ... on StandardPage {
                        commentsCount {
                            total
                            main
                            replies
                            pinned
                            reported
                        }
                        isCommentsEnabled
                    }
                }
            }
            """,
            variables={"id": self.page.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = response.json()

        data = content["data"]["page"]
        self.assertIsNotNone(data["commentsCount"])
        self.assertEqual(data["commentsCount"]["total"], 0)
        self.assertEqual(data["commentsCount"]["main"], 0)
        self.assertEqual(data["commentsCount"]["replies"], 0)
        self.assertEqual(data["commentsCount"]["pinned"], 0)
        self.assertEqual(data["commentsCount"]["reported"], 0)
        self.assertTrue(data["isCommentsEnabled"])

    def test_create_comment_on_wagtail_page(self):
        response = self.query(
            """
            mutation CommentCreate($input: CommentCreateInput!) {
                commentCreate(input: $input) {
                    comment {
                        node {
                            id
                            body
                            target {
                                id
                                commentsCount {
                                    total
                                    replies
                                }
                            }
                        }
                    }
                    errors {
                        field
                        messages
                    }
                }
            }
            """,
            variables={
                "input": {
                    "targetObjectId": self.page.relay_id,
                    "body": "This is a test comment on a Wagtail page",
                }
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = response.json()

        self.assertIsNone(content["data"]["commentCreate"]["errors"])

        comment_data = content["data"]["commentCreate"]["comment"]["node"]
        self.assertEqual(comment_data["body"], "This is a test comment on a Wagtail page")

        target = comment_data["target"]
        self.assertEqual(target["id"], str(self.page.id))
        comments_count = target["commentsCount"]
        self.assertEqual(comments_count["total"], 1)
        self.assertEqual(comments_count["replies"], 0)

    def test_create_reply_comment_on_wagtail_page(self):
        parent_comment = CommentFactory(target=self.page)

        response = self.query(
            """
            mutation CommentCreate($input: CommentCreateInput!) {
                commentCreate(input: $input) {
                    comment {
                        node {
                            id
                            body
                            inReplyTo {
                                id
                                body
                            }
                            target {
                                ... on WagtailPage {
                                    id
                                    commentsCount {
                                        total
                                        main
                                        replies
                                    }
                                }
                            }
                        }
                    }
                    errors {
                        field
                        messages
                    }
                }
            }
            """,
            variables={
                "input": {
                    "targetObjectId": self.page.relay_id,
                    "body": "This is a reply to the parent comment",
                    "inReplyToId": parent_comment.relay_id,
                }
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = response.json()

        self.assertIsNone(content["data"]["commentCreate"]["errors"])

        comment_data = content["data"]["commentCreate"]["comment"]["node"]
        self.assertEqual(comment_data["body"], "This is a reply to the parent comment")

        in_reply_to = comment_data["inReplyTo"]
        self.assertEqual(in_reply_to["id"], parent_comment.relay_id)
        self.assertEqual(in_reply_to["body"], parent_comment.body)

        target = comment_data["target"]
        comments_count = target["commentsCount"]
        self.assertEqual(comments_count["total"], 2)
        self.assertEqual(comments_count["main"], 1)
        self.assertEqual(comments_count["replies"], 1)

    def test_query_comments_on_wagtail_page(self):
        CommentFactory(target=self.page, body="First comment")
        CommentFactory(target=self.page, body="Second comment")

        response = self.query(
            """
            query PageComments($id: ID!) {
                page(id: $id) {
                    id
                    title
                    ... on StandardPage {
                        comments {
                            edges {
                                node {
                                    id
                                    body
                                    user {
                                        id
                                    }
                                    created
                                }
                            }
                        }
                        commentsCount {
                            total
                            main
                        }
                    }
                }
            }
            """,
            variables={"id": self.page.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = response.json()

        data = content["data"]["page"]
        comments = data["comments"]["edges"]

        self.assertEqual(len(comments), 2)
        self.assertEqual(data["commentsCount"]["total"], 2)
        self.assertEqual(data["commentsCount"]["main"], 2)

        comment_bodies = [edge["node"]["body"] for edge in comments]
        self.assertIn("First comment", comment_bodies)
        self.assertIn("Second comment", comment_bodies)

    def test_comments_disabled_on_wagtail_page(self):
        self.page.is_comments_enabled = False
        self.page.save()

        response = self.query(
            """
            mutation CommentCreate($input: CommentCreateInput!) {
                commentCreate(input: $input) {
                    comment {
                        node {
                            id
                            body
                        }
                    }
                    errors {
                        field
                        messages
                    }
                }
            }
            """,
            variables={
                "input": {
                    "targetObjectId": self.page.relay_id,
                    "body": "This comment should not be created",
                }
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = response.json()

        errors = content["errors"]
        self.assertIsNotNone(errors)
        self.assertEqual(errors[0]["extensions"]["code"], "permission_required")

    def test_comments_ordering_and_pagination(self):
        CommentFactory(target=self.page, body="Comment 1")
        CommentFactory(target=self.page, body="Comment 2")
        CommentFactory(target=self.page, body="Comment 3")

        response = self.query(
            """
            query PageComments($id: ID!, $first: Int!) {
                page(id: $id) {
                    id
                    ... on StandardPage {
                        comments(first: $first) {
                            edges {
                                node {
                                    id
                                    body
                                    created
                                }
                                cursor
                            }
                            pageInfo {
                                hasNextPage
                                hasPreviousPage
                            }
                        }
                        commentsCount {
                            total
                        }
                    }
                }
            }
            """,
            variables={"id": self.page.id, "first": 2},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = response.json()

        data = content["data"]["page"]
        comments = data["comments"]["edges"]
        page_info = data["comments"]["pageInfo"]

        self.assertEqual(len(comments), 2)
        self.assertTrue(page_info["hasNextPage"])
        self.assertFalse(page_info["hasPreviousPage"])
        self.assertEqual(data["commentsCount"]["total"], 3)
