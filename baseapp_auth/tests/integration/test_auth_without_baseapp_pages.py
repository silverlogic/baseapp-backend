import pytest

pytestmark = pytest.mark.django_db

ME_WITH_METADATA_GRAPHQL = """
    query {
        me {
            fullName
            metadata {
                metaTitle
            }
        }
    }
"""


@pytest.mark.parametrize("with_disabled_apps", [["baseapp_pages"]], indirect=True)
class TestAuthWithoutBaseappPages:
    def test_me_query_without_metadata(
        self, with_disabled_apps, graphql_user_client, django_user_client
    ):
        response = graphql_user_client(ME_WITH_METADATA_GRAPHQL)
        content = response.json()
        assert content["data"]["me"]["fullName"] == django_user_client.user.get_full_name()
        assert content["data"]["me"]["metadata"] is None
