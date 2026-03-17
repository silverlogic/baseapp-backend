import importlib
from unittest.mock import Mock, patch

import graphene
import pytest
import swapper
from graphene_django.settings import graphene_settings

from baseapp_core.graphql.views import GraphQLView

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

CONTENT_POSTS_WITH_PROFILE_FIELD_GRAPHQL = """
    query {
        contentPosts {
            edges {
                node {
                    content
                    profile {
                        id
                    }
                }
            }
        }
    }
"""


def _build_content_feed_schema_without_profiles_branch():
    from django.apps import apps as django_apps

    original_is_installed = django_apps.is_installed

    def _is_installed_without_profiles(app_name):
        if app_name == "baseapp_profiles":
            return False
        return original_is_installed(app_name)

    with patch.object(django_apps, "is_installed", side_effect=_is_installed_without_profiles):
        object_types_module = importlib.reload(
            importlib.import_module("baseapp.content_feed.graphql.object_types")
        )
        importlib.reload(importlib.import_module("baseapp.content_feed.graphql.queries"))
        queries_module = importlib.import_module("baseapp.content_feed.graphql.queries")
        importlib.reload(importlib.import_module("baseapp.content_feed.graphql.mutations"))
        mutations_module = importlib.import_module("baseapp.content_feed.graphql.mutations")

    class Query(graphene.ObjectType, queries_module.ContentFeedQueries):
        pass

    class Mutation(graphene.ObjectType, mutations_module.ContentFeedMutations):
        pass

    return graphene.Schema(query=Query, mutation=Mutation), object_types_module


@pytest.mark.parametrize("with_disabled_apps", [["baseapp_profiles"]], indirect=True)
class TestContentFeedWithoutBaseappProfiles:
    def test_content_post_create_uses_user_and_skips_profile_assignment(
        self,
        with_disabled_apps,
        django_user_client,
        graphql_user_client,
    ):
        ContentPost = swapper.load_model("baseapp_content_feed", "ContentPost")
        instance = ContentPost(pk=101, content="without profiles", is_reactions_enabled=True)
        instance.save = Mock()
        instance.refresh_from_db = Mock()

        form = Mock()
        form.is_valid.return_value = True
        form.save.return_value = instance

        with (
            patch(
                "baseapp.content_feed.graphql.mutations.ContentPostForm",
                return_value=form,
            ),
            patch(
                "baseapp.content_feed.graphql.mutations.apps.is_installed",
                side_effect=lambda app_name: False if app_name == "baseapp_profiles" else True,
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
        assert instance.user == django_user_client.user
        if hasattr(instance, "profile"):
            assert instance.profile is None

    def test_content_posts_schema_hides_profile_field_when_profiles_disabled(
        self,
        with_disabled_apps,
        graphql_user_client,
    ):
        schema, _ = _build_content_feed_schema_without_profiles_branch()
        with (
            patch.object(graphene_settings, "SCHEMA", schema),
            patch.object(GraphQLView, "schema", schema),
        ):
            response = graphql_user_client(CONTENT_POSTS_WITH_PROFILE_FIELD_GRAPHQL)
        content = response.json()

        assert "errors" in content
        assert any(
            "Cannot query field 'profile' on type 'ContentPost'" in error["message"]
            for error in content["errors"]
        )
