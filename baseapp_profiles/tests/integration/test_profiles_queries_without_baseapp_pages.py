import pytest

from baseapp_profiles.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db

GET_PROFILE_BY_PATH = """
    query Profile($id: ID!) {
        profile(id: $id) {
            id
            name
            metadata {
                metaTitle
                metaOgImage(width: 100, height: 100) {
                    url
                }
            }
        }
    }
"""


@pytest.mark.parametrize("with_disabled_apps", [["baseapp_pages"]], indirect=True)
class TestProfilesQueriesWithoutBaseappPages:
    def test_profiles_queries_without_baseapp_pages(self, with_disabled_apps, graphql_user_client):
        profile = ProfileFactory()
        response = graphql_user_client(GET_PROFILE_BY_PATH, variables={"id": profile.relay_id})
        content = response.json()
        assert content["data"]["profile"]["id"] == profile.relay_id
        assert content["data"]["profile"]["name"] == profile.name
        assert content["data"]["profile"]["metadata"] is None
