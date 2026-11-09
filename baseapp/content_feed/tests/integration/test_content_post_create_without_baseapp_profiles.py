from unittest.mock import Mock, patch

import pytest
import swapper
from django.apps import apps as django_apps

from baseapp.content_feed.strawberry.types import content_post_relations

pytestmark = pytest.mark.django_db

CONTENT_POST_CREATE_GRAPHQL = """
    mutation ContentPostCreate($input: ContentPostCreateInput!) {
        contentPostCreate(input: $input) {
            contentPost {
                node {
                    content
                    isReactionsEnabled
                }
            }
            errors {
                field
                messages
            }
        }
    }
"""


@pytest.mark.parametrize("with_disabled_apps", [["baseapp_profiles"]], indirect=True)
class TestContentFeedWithoutBaseappProfiles:
    def test_content_post_create_uses_user_and_skips_profile_assignment(
        self,
        with_disabled_apps,
        django_user_client,
        graphql_user_client,
    ) -> None:
        ContentPost = swapper.load_model("baseapp_content_feed", "ContentPost")
        instance = ContentPost(pk=101, content="without profiles")
        instance.save = Mock()
        instance.refresh_from_db = Mock()

        form = Mock()
        form.is_valid.return_value = True
        form.save.return_value = instance

        # Stub the reactable_metadata service so the mutation's write-through doesn't
        # try to insert into the (absent) metadata table for our pk=101 fake, and so
        # the GraphQL `isReactionsEnabled` resolver returns the True we'd expect.
        reactable_service = Mock()
        reactable_service.is_reactions_enabled.return_value = True

        def _shared_services_get(name) -> Mock | None:
            if name == "reactable_metadata":
                return reactable_service
            return None

        with (
            patch(
                "baseapp.content_feed.strawberry.mutations.ContentPostForm",
                return_value=form,
            ),
            patch(
                "baseapp.content_feed.strawberry.mutations.apps.is_installed",
                side_effect=lambda app_name: False if app_name == "baseapp_profiles" else True,
            ),
            # One shared registry: also stubs the `isReactionsEnabled` resolver's lookup.
            patch(
                "baseapp.content_feed.strawberry.mutations.shared_services.get",
                side_effect=_shared_services_get,
            ),
        ):
            response = graphql_user_client(
                CONTENT_POST_CREATE_GRAPHQL,
                variables={
                    "input": {
                        "content": "without profiles",
                        "isReactionsEnabled": True,
                    }
                },
            )
            content = response.json()

        assert "errors" not in content
        assert content["data"]["contentPostCreate"]["errors"] is None
        assert content["data"]["contentPostCreate"]["contentPost"]["node"]["content"] == (
            "without profiles"
        )
        assert content["data"]["contentPostCreate"]["contentPost"]["node"]["isReactionsEnabled"]
        # The mutation should write the input through to the metadata service.
        reactable_service.set_is_reactions_enabled.assert_called_once_with(instance, True)
        assert instance.user == django_user_client.user
        if hasattr(instance, "profile"):
            assert instance.profile is None

    def test_content_post_type_hides_profile_field_when_profiles_disabled(
        self, with_disabled_apps
    ) -> None:
        original = django_apps.is_installed
        with patch.object(
            django_apps,
            "is_installed",
            side_effect=lambda name: name != "baseapp_profiles" and original(name),
        ):
            assert content_post_relations() == ("user",)
