from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import swapper

from baseapp_comments.permissions import CommentsPermissionsBackend

pytestmark = pytest.mark.django_db

COMMENT_CREATE_GRAPHQL = """
mutation CommentCreateMutation($input: CommentCreateInput!) {
  commentCreate(input: $input) {
    comment {
      node {
        body
      }
    }
    errors {
      field
      messages
    }
  }
}
"""

ALL_COMMENTS_QUERY = """
query AllComments {
  allComments {
    edges {
      node {
        body
      }
    }
  }
}
"""


@pytest.mark.parametrize("with_disabled_apps", [["baseapp_profiles"]], indirect=True)
class TestCommentsWithoutBaseappProfiles:
    def test_comment_create_uses_user_path_without_profile_permission_branch(
        self, with_disabled_apps, django_user_client, graphql_user_client
    ):
        Comment = swapper.load_model("baseapp_comments", "Comment")
        target = Comment(pk=10, is_comments_enabled=True)
        target.refresh_from_db = Mock()
        fake_form = Mock()
        fake_form.is_valid.return_value = True
        fake_form.save.return_value = None

        user_class = type(django_user_client.user)
        with (
            patch.object(
                user_class,
                "has_perm",
                autospec=True,
                wraps=user_class.has_perm,
            ) as has_perm_mock,
            patch(
                "baseapp_comments.graphql.mutations.get_obj_from_relay_id",
                return_value=target,
            ),
            patch(
                "baseapp_comments.graphql.mutations.CommentForm",
                return_value=fake_form,
            ) as comment_form_cls,
        ):
            response = graphql_user_client(
                COMMENT_CREATE_GRAPHQL,
                variables={"input": {"targetObjectId": "target-relay-id", "body": "my comment"}},
            )
            content = response.json()

        assert "errors" not in content
        assert content["data"]["commentCreate"]["comment"]["node"]["body"] == "my comment"
        assert comment_form_cls.called
        called_perms = [call.args[1] for call in has_perm_mock.call_args_list if len(call.args) > 1]
        assert any(perm.endswith(".add_comment") for perm in called_perms)
        assert not any(perm.endswith(".add_comment_with_profile") for perm in called_perms)

    def test_all_comments_query_uses_blocks_lookup_service_without_profiles(
        self, with_disabled_apps, django_user_client, graphql_user_client
    ):
        Comment = swapper.load_model("baseapp_comments", "Comment")
        base_queryset = Comment.objects.none()
        filtered_queryset = Comment.objects.none()
        mock_service = Mock()
        mock_service.exclude_blocked_from_foreign_queryset.return_value = filtered_queryset

        with (
            patch(
                "baseapp_comments.graphql.queries.CommentObjectType._meta.model.objects.all",
                return_value=base_queryset,
            ),
            patch(
                "baseapp_comments.graphql.object_types.shared_services.get",
                return_value=mock_service,
            ),
        ):
            response = graphql_user_client(ALL_COMMENTS_QUERY)
            content = response.json()

        assert "errors" not in content
        assert content["data"]["allComments"]["edges"] == []
        mock_service.exclude_blocked_from_foreign_queryset.assert_called_once()
        call = mock_service.exclude_blocked_from_foreign_queryset.call_args
        assert getattr(call.args[0], "model", None) is Comment

    def test_add_comment_with_profile_permission_is_disabled_without_profiles(
        self, with_disabled_apps
    ):
        backend = CommentsPermissionsBackend()
        user = SimpleNamespace(
            is_authenticated=True,
            id=100,
            has_perm=Mock(return_value=True),
        )

        has_perm = backend.has_perm(
            user,
            "baseapp_comments.add_comment_with_profile",
            object(),
        )

        assert not has_perm
