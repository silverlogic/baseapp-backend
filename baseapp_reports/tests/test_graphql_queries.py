import pytest
import swapper

from baseapp_profiles.tests.factories import ProfileFactory

Report = swapper.load_model("baseapp_reports", "Report")

pytestmark = pytest.mark.django_db

REPORT_TYPES_LIST_GRAPHQL = """
query reportTypesQuery($topLevelOnly: Boolean!, $targetObjectId: String!) {
    allReportTypes(topLevelOnly: $topLevelOnly, targetObjectId: $targetObjectId) {
        edges {
            node {
                id
                key
                label
            }
        }
    }
}
"""


def test_anon_can_list_report_types(graphql_client):
    profile = ProfileFactory()

    variables = {
        "targetObjectId": profile.relay_id,
        "topLevelOnly": True,
    }

    response = graphql_client(REPORT_TYPES_LIST_GRAPHQL, variables=variables)
    content = response.json()

    assert "errors" not in content
    assert len(content["data"]["allReportTypes"]["edges"]) > 0
