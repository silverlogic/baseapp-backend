from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import swapper

from baseapp_ratings.permissions import RatingsPermissionsBackend

pytestmark = pytest.mark.django_db


RATE_CREATE_GRAPHQL = """
mutation RateCreateMutation($input: RateCreateInput!) {
  rateCreate(input: $input) {
    rate {
      node {
        value
      }
    }
  }
}
"""

MY_RATING_QUERY = """
query MyRating($id: ID!) {
  node(id: $id) {
    ... on RatingsInterface {
      myRating {
        value
      }
    }
  }
}
"""


@pytest.mark.parametrize("with_disabled_apps", [["baseapp_profiles"]], indirect=True)
class TestRatingsWithoutBaseappProfiles:
    def test_mutation_uses_user_based_create_when_profiles_disabled(
        self, with_disabled_apps, django_user_client, graphql_user_client
    ):
        RateModel = swapper.load_model("baseapp_ratings", "Rate")
        target = SimpleNamespace(pk=10, is_ratings_enabled=True, refresh_from_db=Mock())
        fake_rate = RateModel(pk=1, value=4, user=django_user_client.user)
        fake_content_type = object()

        with (
            patch(
                "baseapp_ratings.graphql.mutations.get_obj_from_relay_id",
                return_value=target,
            ),
            patch(
                "baseapp_ratings.graphql.mutations.ContentType.objects.get_for_model",
                return_value=fake_content_type,
            ),
            patch(
                "baseapp_ratings.graphql.mutations.RateModel.objects.create",
                return_value=fake_rate,
            ) as create_rate,
        ):
            response = graphql_user_client(
                RATE_CREATE_GRAPHQL,
                variables={"input": {"targetObjectId": "target-relay-id", "value": 4}},
            )
            content = response.json()

        assert "errors" not in content
        assert content["data"]["rateCreate"]["rate"]["node"]["value"] == 4
        _, kwargs = create_rate.call_args
        assert kwargs["user"] == django_user_client.user
        assert kwargs["target_object_id"] == 10
        assert kwargs["target_content_type"] is fake_content_type
        assert kwargs["value"] == 4

    def test_mutation_ignores_profile_id_when_profiles_disabled(
        self, with_disabled_apps, django_user_client, graphql_user_client
    ):
        RateModel = swapper.load_model("baseapp_ratings", "Rate")
        target = SimpleNamespace(pk=11, is_ratings_enabled=True, refresh_from_db=Mock())

        with (
            patch(
                "baseapp_ratings.graphql.mutations.get_obj_from_relay_id",
                return_value=target,
            ),
            patch(
                "baseapp_ratings.graphql.mutations.ContentType.objects.get_for_model",
                return_value=object(),
            ),
            patch(
                "baseapp_ratings.graphql.mutations.RateModel.objects.create",
                return_value=RateModel(pk=2, value=5, user=django_user_client.user),
            ),
            patch("baseapp_ratings.graphql.mutations.get_pk_from_relay_id") as get_pk_from_relay_id,
        ):
            response = graphql_user_client(
                RATE_CREATE_GRAPHQL,
                variables={
                    "input": {
                        "targetObjectId": "target-relay-id",
                        "profileId": "profile-relay-id",
                        "value": 5,
                    }
                },
            )
            content = response.json()

        assert "errors" not in content
        get_pk_from_relay_id.assert_not_called()

    def test_my_rating_resolves_using_current_user_when_profiles_disabled(
        self, with_disabled_apps, django_user_client, graphql_user_client
    ):
        RateModel = swapper.load_model("baseapp_ratings", "Rate")
        User = swapper.load_model("users", "User")

        root = User(pk=200)
        fake_rate = RateModel(pk=3, value=5, user=django_user_client.user)
        fake_content_type = object()
        queryset = Mock()
        queryset.first.return_value = fake_rate

        with (
            patch(
                "baseapp_core.graphql.relay.Node.get_node_from_global_id",
                return_value=root,
            ),
            patch(
                "baseapp_ratings.graphql.object_types.ContentType.objects.get_for_model",
                return_value=fake_content_type,
            ),
            patch(
                "baseapp_ratings.graphql.object_types.RateModel.objects.filter",
                return_value=queryset,
            ) as rate_filter,
        ):
            response = graphql_user_client(
                MY_RATING_QUERY,
                variables={"id": "target-relay-id"},
            )
            content = response.json()

        assert "errors" not in content
        assert content["data"]["node"]["myRating"]["value"] == 5
        rate_filter.assert_called_once_with(
            target_content_type=fake_content_type,
            target_object_id=200,
            user=django_user_client.user,
        )

    def test_add_rate_with_profile_permission_is_disabled_without_profiles(
        self, with_disabled_apps
    ):
        backend = RatingsPermissionsBackend()
        user = SimpleNamespace(
            is_authenticated=True,
            id=100,
            has_perm=Mock(return_value=True),
        )

        has_perm = backend.has_perm(
            user,
            "baseapp_ratings.add_rate_with_profile",
            object(),
        )

        assert has_perm is False
