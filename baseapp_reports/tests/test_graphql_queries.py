import pytest
import swapper

from baseapp_profiles.tests.factories import ProfileFactory

Report = swapper.load_model("baseapp_reports", "Report")

pytestmark = pytest.mark.django_db


REPORT_TYPES_LIST_GRAPHQL = """
query reportTypesQuery($topLevelOnly: Boolean, $targetObjectId: String) {
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
    response = graphql_client(REPORT_TYPES_LIST_GRAPHQL)
    content = response.json()
    assert "errors" not in content
    assert len(content["data"]["allReportTypes"]["edges"]) > 0


def test_anon_can_get_report_type_filtered_by_top_level(graphql_client):
    response = graphql_client(REPORT_TYPES_LIST_GRAPHQL, variables={"topLevelOnly": True})
    content = response.json()
    assert (
        len(content["data"]["allReportTypes"]["edges"]) == 8
    )  # 11 total created by baseapp_reports migrations, with 3 subtypes


def test_anon_can_get_report_type_filtered_by_content_type(graphql_client):
    other_profile = ProfileFactory()
    response = graphql_client(
        REPORT_TYPES_LIST_GRAPHQL, variables={"targetObjectId": other_profile.relay_id}
    )
    content = response.json()
    assert (
        len(content["data"]["allReportTypes"]["edges"]) == 8
    )  # 11 total, with 3 being exclusive to comments
