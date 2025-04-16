import pytest
import swapper

from baseapp.activity_log.models import ActivityLog, VisibilityTypes
from baseapp_comments.tests.factories import CommentFactory
from baseapp_profiles.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db

Comment = swapper.load_model("baseapp_comments", "Comment")
Profile = swapper.load_model("baseapp_profiles", "Profile")

COMMENT_CREATE_GRAPHQL = """
    mutation CommentCreateMutation($input: CommentCreateInput!) {
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
            _debug {
                exceptions {
                    stack
                }
            }
        }
    }
"""


@pytest.mark.celery_app
def test_add_comment_is_public(django_user_client, graphql_user_client, celery_config):
    target = CommentFactory()

    graphql_user_client(
        COMMENT_CREATE_GRAPHQL,
        variables={"input": {"targetObjectId": target.relay_id, "body": "my comment"}},
    )

    activity = ActivityLog.objects.get()

    assert activity.visibility == VisibilityTypes.PUBLIC
    assert activity.user_id == django_user_client.user.pk
    assert activity.profile_id == django_user_client.user.profile.pk
    assert activity.verb == f"{Comment._meta.app_label}.add_comment"


PROFILE_UPDATE_GRAPHQL = """
    mutation ProfileUpdateMutation($input: ProfileUpdateInput!) {
        profileUpdate(input: $input) {
            profile {
                id
                name
                biography
                image(width: 100, height: 100) {
                    url
                }
                bannerImage(width: 100, height: 100) {
                    url
                }
            }
            errors {
                field
                messages
            }
        }
    }
"""


@pytest.mark.celery_app
def test_update_profile_is_public(django_user_client, graphql_user_client, celery_config):
    profile = ProfileFactory(owner=django_user_client.user)

    graphql_user_client(
        PROFILE_UPDATE_GRAPHQL,
        variables={"input": {"id": profile.relay_id, "biography": "my edited profile"}},
    )

    activity = ActivityLog.objects.get()

    assert activity.visibility == VisibilityTypes.PUBLIC
    assert activity.user_id == django_user_client.user.pk
    assert activity.profile_id == django_user_client.user.profile.pk
    assert activity.verb == "baseapp_profiles.update_profile"
