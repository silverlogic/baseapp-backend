import pytest
import swapper
from django.contrib.auth.models import Permission

from baseapp_blocks.tests.factories import BlockFactory
from baseapp_profiles.tests.factories import ProfileFactory

from .factories import CommentFactory

pytestmark = pytest.mark.django_db

VIEW_ALL_QUERY = """
    query {
        allComments {
            totalCount
            edges {
                node {
                    id
                    body
                    commentsCount {
                        main
                    }
                    comments {
                        edges {
                            node {
                                id
                                body
                            }
                        }
                    }
                }
            }
        }
    }
"""

Comment = swapper.load_model("baseapp_comments", "Comment")
app_label = Comment._meta.app_label


def test_user_cant_see_comment_made_by_bloker_profile(django_user_client, graphql_user_client):
    """
    Scenario:
        - Current User is blocked by another user.
        - Current the blocker has one comment.
        - current user does not have any comment.
    Expected behavior:
        - The user can't see the comment made by the blocker.
        - The user can't see any comment.
    """

    perm = Permission.objects.get(content_type__app_label=app_label, codename="view_all_comments")
    django_user_client.user.user_permissions.add(perm)

    current_user_profile = ProfileFactory(owner=django_user_client.user)
    blocked_profile = ProfileFactory()

    BlockFactory(actor=current_user_profile, target=blocked_profile)

    CommentFactory(profile=blocked_profile, user=blocked_profile.owner)

    response = graphql_user_client(
        VIEW_ALL_QUERY, headers={"HTTP_CURRENT_PROFILE": current_user_profile.relay_id}
    )
    content = response.json()

    assert content["data"]["allComments"]["totalCount"] == 0
    assert len(content["data"]["allComments"]["edges"]) == 0


def test_user_cant_see_comment_made_by_bloked_profile(django_user_client, graphql_user_client):
    """
    Scenario:
        - Current User has a profile blocked.
        - Current User has one comment.
        - Bloked profile has one comment.
    Expected behavior:
        - The user can only see his own comment.
        - The user can't see the comment made by blocked profile.
    """

    perm = Permission.objects.get(content_type__app_label=app_label, codename="view_all_comments")
    django_user_client.user.user_permissions.add(perm)

    current_user_profile = ProfileFactory(owner=django_user_client.user)
    current_user_profile.refresh_from_db()
    blocked_profile = ProfileFactory()

    BlockFactory(actor=current_user_profile, target=blocked_profile)

    comment = CommentFactory(user=django_user_client.user, profile=current_user_profile)

    CommentFactory(profile=blocked_profile, user=blocked_profile.owner)

    response = graphql_user_client(
        VIEW_ALL_QUERY, headers={"HTTP_CURRENT_PROFILE": current_user_profile.relay_id}
    )
    content = response.json()

    assert content["data"]["allComments"]["totalCount"] == 1
    assert len(content["data"]["allComments"]["edges"]) == 1
    assert content["data"]["allComments"]["edges"][0]["node"]["body"] == comment.body
