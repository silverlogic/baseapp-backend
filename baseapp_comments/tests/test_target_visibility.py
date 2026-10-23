from types import SimpleNamespace

import pytest
import swapper
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from django.conf import settings
from django.contrib.auth.models import Permission
from django.test import override_settings
from graphene_django.settings import graphene_settings

from baseapp.content_feed.tests.factories import ContentPostFactory
from baseapp_comments.graphql.subscriptions import OnCommentChange
from baseapp_comments.permissions import CommentsPermissionsBackend
from baseapp_core.tests.factories import UserFactory
from baseapp_pages.tests.factories import PageFactory
from baseapp_reports.tests.factories import ReportTypeFactory

from .factories import CommentFactory
from .test_graphql_subscriptions import SUBSCRIPTION_QUERY

Comment = swapper.load_model("baseapp_comments", "Comment")
Page = swapper.load_model("baseapp_pages", "Page")
Reaction = swapper.load_model("baseapp_reactions", "Reaction")
Report = swapper.load_model("baseapp_reports", "Report")
Notification = swapper.load_model("notifications", "Notification")
app_label = Comment._meta.app_label

pytestmark = pytest.mark.django_db


class StaffOnlyPageCommentsBackend(CommentsPermissionsBackend):
    """Comments on pages are readable by staff only; every other target keeps the defaults."""

    def has_perm(self, user_obj, perm, obj=None) -> bool | None:
        if perm == f"{app_label}.view_target_comments" and isinstance(obj, Page):
            return user_obj.is_staff
        return super().has_perm(user_obj, perm, obj)


def _backends_with(backend_path: str) -> list[str]:
    default = "baseapp_comments.permissions.CommentsPermissionsBackend"
    return [backend_path if b == default else b for b in settings.AUTHENTICATION_BACKENDS]


staff_only_page_comments = override_settings(
    AUTHENTICATION_BACKENDS=_backends_with(
        "baseapp_comments.tests.test_target_visibility.StaffOnlyPageCommentsBackend"
    )
)

TARGET_COMMENTS_QUERY = """
    query TargetComments($id: ID!) {
        node(id: $id) {
            ... on CommentsInterface {
                commentsCount {
                    total
                    main
                }
                comments {
                    edges {
                        node {
                            id
                        }
                    }
                }
            }
        }
    }
"""

COMMENT_NODE_QUERY = """
    query CommentNode($id: ID!) {
        comment(id: $id) {
            id
            body
        }
    }
"""


def _target_comments(client, target) -> tuple[int, list[str]]:
    content = client(TARGET_COMMENTS_QUERY, variables={"id": target.relay_id}).json()
    assert "errors" not in content, content
    node = content["data"]["node"]
    return node["commentsCount"]["total"], [e["node"]["id"] for e in node["comments"]["edges"]]


def test_target_comments_are_visible_by_default(graphql_user_client) -> None:
    page = PageFactory()
    comment = CommentFactory(target=page)

    total, ids = _target_comments(graphql_user_client, page)

    assert total == 1
    assert ids == [comment.relay_id]


@staff_only_page_comments
def test_comments_and_count_are_hidden_when_target_is_restricted(graphql_user_client) -> None:
    page = PageFactory()
    CommentFactory(target=page)

    total, ids = _target_comments(graphql_user_client, page)

    assert total == 0
    assert ids == []


@staff_only_page_comments
def test_comments_of_other_targets_keep_the_defaults(graphql_user_client) -> None:
    target = ContentPostFactory()
    comment = CommentFactory(target=target)

    total, ids = _target_comments(graphql_user_client, target)

    assert total == 1
    assert ids == [comment.relay_id]


@staff_only_page_comments
def test_comments_are_visible_when_target_is_permitted(
    django_user_client, graphql_user_client
) -> None:
    django_user_client.user.is_staff = True
    django_user_client.user.save()
    page = PageFactory()
    comment = CommentFactory(target=page)

    total, ids = _target_comments(graphql_user_client, page)

    assert total == 1
    assert ids == [comment.relay_id]


@staff_only_page_comments
def test_comment_node_is_hidden_when_target_is_restricted(graphql_user_client) -> None:
    comment = CommentFactory(target=PageFactory())

    content = graphql_user_client(COMMENT_NODE_QUERY, variables={"id": comment.relay_id}).json()

    assert content["data"]["comment"] is None


@staff_only_page_comments
def test_comment_node_is_visible_when_target_is_permitted(
    django_user_client, graphql_user_client
) -> None:
    django_user_client.user.is_staff = True
    django_user_client.user.save()
    comment = CommentFactory(target=PageFactory())

    content = graphql_user_client(COMMENT_NODE_QUERY, variables={"id": comment.relay_id}).json()

    assert content["data"]["comment"]["id"] == comment.relay_id


@override_settings(BASEAPP_COMMENTS_CAN_ANONYMOUS_VIEW_COMMENTS=False)
def test_anonymous_viewing_off_still_hides_the_comments_list(graphql_client) -> None:
    page = PageFactory()
    CommentFactory(target=page)

    _total, ids = _target_comments(graphql_client, page)

    assert ids == []


def test_default_backend_grants_view_target_comments_and_view_comment(django_user_client) -> None:
    comment = CommentFactory(target=PageFactory())
    user = django_user_client.user

    assert user.has_perm(f"{app_label}.view_target_comments", comment.target)
    assert user.has_perm(f"{app_label}.view_target_comments", comment)
    assert user.has_perm(f"{app_label}.view_comment", comment)


def _subscription_groups(user, target_relay_id: str) -> list[str]:
    info = SimpleNamespace(
        context=SimpleNamespace(channels_scope={"user": user}),
        schema=graphene_settings.SCHEMA.graphql_schema,
    )
    return async_to_sync(OnCommentChange.subscribe)(None, info, target_object_id=target_relay_id)


@pytest.mark.django_db(transaction=True)
@staff_only_page_comments
def test_subscribe_joins_no_group_for_a_restricted_target(django_user_client) -> None:
    page = PageFactory()

    assert _subscription_groups(django_user_client.user, page.relay_id) == []


@pytest.mark.django_db(transaction=True)
@staff_only_page_comments
def test_subscribe_joins_the_target_group_when_permitted(django_user_client) -> None:
    django_user_client.user.is_staff = True
    django_user_client.user.save()
    page = PageFactory()

    assert _subscription_groups(django_user_client.user, page.relay_id) == [page.relay_id]


async def _subscribe(client, target_relay_id: str | None) -> str:
    variables = {"targetObjectId": target_relay_id} if target_relay_id else {}
    sub_id = await client.send(
        msg_type="subscribe",
        payload={"query": SUBSCRIPTION_QUERY, "operationName": "op_name", "variables": variables},
    )
    await client.assert_no_messages()
    return sub_id


async def _create_comment(target) -> str:
    comment = await database_sync_to_async(CommentFactory)(target=target)
    return await database_sync_to_async(lambda: comment.relay_id)()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@staff_only_page_comments
async def test_cant_subscribe_to_a_restricted_target(graphql_ws_user_client) -> None:
    client = await graphql_ws_user_client(consumer_attrs={"strict_ordering": True})
    page = await database_sync_to_async(PageFactory)()
    page_relay_id = await database_sync_to_async(lambda: page.relay_id)()

    await _subscribe(client, page_relay_id)
    await _create_comment(page)

    await client.assert_no_messages()
    await client.finalize()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@staff_only_page_comments
async def test_can_subscribe_to_a_permitted_target(
    graphql_ws_user_client, django_user_client
) -> None:
    django_user_client.user.is_staff = True
    await database_sync_to_async(django_user_client.user.save)()
    client = await graphql_ws_user_client(consumer_attrs={"strict_ordering": True})
    page = await database_sync_to_async(PageFactory)()
    page_relay_id = await database_sync_to_async(lambda: page.relay_id)()

    sub_id = await _subscribe(client, page_relay_id)
    comment_relay_id = await _create_comment(page)

    resp = await client.receive(assert_id=sub_id, assert_type="next")
    assert resp["data"]["onCommentChange"]["createdComment"]["node"]["id"] == comment_relay_id
    await client.finalize()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_cant_subscribe_to_an_unknown_target(graphql_ws_user_client) -> None:
    client = await graphql_ws_user_client(consumer_attrs={"strict_ordering": True})

    await _subscribe(client, "UGFnZTo5OTk5OTk=")  # Page:999999
    await _subscribe(client, "not-a-relay-id")
    await client.assert_no_messages()
    await client.finalize()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@staff_only_page_comments
async def test_publish_skips_comments_the_subscriber_cant_view(
    graphql_ws_user_client, django_user_client
) -> None:
    """The "all" group carries every target, so publish re-checks each comment."""
    perm = await Permission.objects.aget(
        content_type__app_label=app_label, codename="view_all_comments"
    )
    await database_sync_to_async(django_user_client.user.user_permissions.add)(perm)
    client = await graphql_ws_user_client(consumer_attrs={"strict_ordering": True})
    page = await database_sync_to_async(PageFactory)()
    other_target = await database_sync_to_async(ContentPostFactory)()

    sub_id = await _subscribe(client, None)
    await _create_comment(page)
    visible_relay_id = await _create_comment(other_target)

    # The factory saves twice, so each comment is broadcast as created, then updated.
    created = await client.receive(assert_id=sub_id, assert_type="next")
    updated = await client.receive(assert_id=sub_id, assert_type="next")
    assert created["data"]["onCommentChange"]["createdComment"]["node"]["id"] == visible_relay_id
    assert updated["data"]["onCommentChange"]["updatedComment"]["id"] == visible_relay_id
    await client.assert_no_messages()
    await client.finalize()


REACTION_TOGGLE_GRAPHQL = """
    mutation ReactionToggle($input: ReactionToggleInput!) {
        reactionToggle(input: $input) {
            target { ... on Comment { id body } }
            reaction { node { target { ... on Comment { id body } } } }
        }
    }
"""

REPORT_CREATE_GRAPHQL = """
    mutation ReportCreate($input: ReportCreateInput!) {
        reportCreate(input: $input) {
            report { node { target { ... on Comment { id body } } } }
        }
    }
"""

COMMENT_CREATE_GRAPHQL = """
    mutation CommentCreate($input: CommentCreateInput!) {
        commentCreate(input: $input) {
            comment { node { id body target { ... on Comment { body } } inReplyTo { body } } }
        }
    }
"""

COMMENT_RELATIONS_QUERY = """
    query CommentRelations($id: ID!) {
        comment(id: $id) {
            id
            inReplyTo { id body }
            target { ... on Comment { id body } }
        }
    }
"""

COMMENT_DELETE_GRAPHQL = """
    mutation CommentDelete($input: CommentDeleteInput!) {
        commentDelete(input: $input) {
            deletedId
            inReplyTo { id body }
            target { ... on Comment { id body } }
        }
    }
"""


def _permission_error(content: dict) -> bool:
    return content["errors"][0]["extensions"]["code"] == "permission_required"


@staff_only_page_comments
def test_cant_react_to_a_restricted_comment(graphql_user_client) -> None:
    secret = CommentFactory(target=PageFactory(), body="secret")

    content = graphql_user_client(
        REACTION_TOGGLE_GRAPHQL,
        variables={"input": {"targetObjectId": secret.relay_id, "reactionType": "LIKE"}},
    ).json()

    assert _permission_error(content)
    assert content["data"]["reactionToggle"] is None
    assert not Reaction.objects.exists()


@staff_only_page_comments
def test_staff_can_react_to_a_restricted_comment(django_user_client, graphql_user_client) -> None:
    django_user_client.user.is_staff = True
    django_user_client.user.save()
    comment = CommentFactory(target=PageFactory(), body="internal")

    content = graphql_user_client(
        REACTION_TOGGLE_GRAPHQL,
        variables={"input": {"targetObjectId": comment.relay_id, "reactionType": "LIKE"}},
    ).json()

    assert "errors" not in content, content
    assert content["data"]["reactionToggle"]["target"]["body"] == "internal"


@staff_only_page_comments
def test_cant_report_a_restricted_comment(graphql_user_client) -> None:
    secret = CommentFactory(target=PageFactory(), body="secret")

    content = graphql_user_client(
        REPORT_CREATE_GRAPHQL,
        variables={
            "input": {
                "targetObjectId": secret.relay_id,
                "reportTypeId": ReportTypeFactory().relay_id,
            }
        },
    ).json()

    assert _permission_error(content)
    assert content["data"]["reportCreate"] is None
    assert not Report.objects.exists()


@staff_only_page_comments
def test_cant_reply_to_a_restricted_comment_from_another_target(graphql_user_client) -> None:
    secret = CommentFactory(target=PageFactory(), body="secret")

    content = graphql_user_client(
        COMMENT_CREATE_GRAPHQL,
        variables={
            "input": {
                "targetObjectId": ContentPostFactory().relay_id,
                "inReplyToId": secret.relay_id,
                "body": "reply",
            }
        },
    ).json()

    assert _permission_error(content)
    assert not Comment.objects.filter(body="reply").exists()


@staff_only_page_comments
def test_cant_comment_on_a_restricted_comment(graphql_user_client) -> None:
    secret = CommentFactory(target=PageFactory(), body="secret")

    content = graphql_user_client(
        COMMENT_CREATE_GRAPHQL,
        variables={"input": {"targetObjectId": secret.relay_id, "body": "comment"}},
    ).json()

    assert _permission_error(content)
    assert not Comment.objects.filter(body="comment").exists()


def test_can_reply_to_and_comment_on_a_visible_comment(graphql_user_client) -> None:
    target = ContentPostFactory()
    parent = CommentFactory(target=target, body="parent")

    reply = graphql_user_client(
        COMMENT_CREATE_GRAPHQL,
        variables={
            "input": {
                "targetObjectId": target.relay_id,
                "inReplyToId": parent.relay_id,
                "body": "r",
            }
        },
    ).json()
    nested = graphql_user_client(
        COMMENT_CREATE_GRAPHQL,
        variables={"input": {"targetObjectId": parent.relay_id, "body": "n"}},
    ).json()

    assert reply["data"]["commentCreate"]["comment"]["node"]["inReplyTo"]["body"] == "parent"
    assert nested["data"]["commentCreate"]["comment"]["node"]["target"]["body"] == "parent"


@staff_only_page_comments
def test_in_reply_to_and_target_hide_a_restricted_comment(graphql_user_client) -> None:
    """Rows written before the gate, or by staff, can link a visible comment to a hidden one."""
    secret = CommentFactory(target=PageFactory(), body="secret")
    reply = CommentFactory(target=ContentPostFactory(), in_reply_to=secret)
    nested = CommentFactory(target=secret)

    reply_content = graphql_user_client(
        COMMENT_RELATIONS_QUERY, variables={"id": reply.relay_id}
    ).json()
    nested_content = graphql_user_client(
        COMMENT_RELATIONS_QUERY, variables={"id": nested.relay_id}
    ).json()

    assert reply_content["data"]["comment"]["id"] == reply.relay_id
    assert reply_content["data"]["comment"]["inReplyTo"] is None
    assert nested_content["data"]["comment"]["id"] == nested.relay_id
    assert nested_content["data"]["comment"]["target"] is None


@staff_only_page_comments
def test_in_reply_to_and_target_are_visible_when_permitted(
    django_user_client, graphql_user_client
) -> None:
    django_user_client.user.is_staff = True
    django_user_client.user.save()
    parent = CommentFactory(target=PageFactory(), body="internal")
    reply = CommentFactory(target=ContentPostFactory(), in_reply_to=parent)
    nested = CommentFactory(target=parent)

    reply_content = graphql_user_client(
        COMMENT_RELATIONS_QUERY, variables={"id": reply.relay_id}
    ).json()
    nested_content = graphql_user_client(
        COMMENT_RELATIONS_QUERY, variables={"id": nested.relay_id}
    ).json()

    assert reply_content["data"]["comment"]["inReplyTo"]["body"] == "internal"
    assert nested_content["data"]["comment"]["target"]["body"] == "internal"


@staff_only_page_comments
def test_comment_delete_payload_hides_a_restricted_parent(
    django_user_client, graphql_user_client
) -> None:
    secret = CommentFactory(target=PageFactory(), body="secret")
    reply = CommentFactory(
        target=ContentPostFactory(), in_reply_to=secret, user=django_user_client.user
    )

    content = graphql_user_client(
        COMMENT_DELETE_GRAPHQL, variables={"input": {"id": reply.relay_id}}
    ).json()

    assert content["data"]["commentDelete"]["deletedId"] == reply.relay_id
    assert content["data"]["commentDelete"]["inReplyTo"] is None


@override_settings(BASEAPP_COMMENTS_ENABLE_NOTIFICATIONS=True)
@staff_only_page_comments
def test_no_comment_notifications_to_users_who_cant_view_them() -> None:
    owner = UserFactory()
    page = PageFactory(user=owner)
    parent = CommentFactory(target=page, user=owner)

    CommentFactory(target=page)
    CommentFactory(target=page, in_reply_to=parent)

    assert not Notification.objects.filter(recipient=owner).exists()


@override_settings(BASEAPP_COMMENTS_ENABLE_NOTIFICATIONS=True)
@staff_only_page_comments
def test_comment_notifications_reach_users_who_can_view_them() -> None:
    owner = UserFactory(is_staff=True)
    page = PageFactory(user=owner)
    parent = CommentFactory(target=page, user=owner)

    CommentFactory(target=page)
    CommentFactory(target=page, in_reply_to=parent)

    verbs = set(Notification.objects.filter(recipient=owner).values_list("verb", flat=True))
    assert verbs == {"COMMENTS.COMMENT_CREATED", "COMMENTS.COMMENT_REPLY_CREATED"}
