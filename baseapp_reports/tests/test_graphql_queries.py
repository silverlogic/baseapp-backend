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
    profile = ProfileFactory()

    variables = {
        "targetObjectId": profile.relay_id,
        "topLevelOnly": True,
    }

    response = graphql_client(REPORT_TYPES_LIST_GRAPHQL, variables=variables)
    content = response.json()

    assert "errors" not in content
    assert len(content["data"]["allReportTypes"]["edges"]) > 0


def test_user_can_get_report_types(django_user_client, graphql_user_client):
    response = graphql_user_client(REPORT_TYPES_LIST_GRAPHQL, variables={})
    content = response.json()

    assert (
        len(content["data"]["allReportTypes"]["edges"]) == 11
    )  # Created by baseapp_reports migrations


def test_user_can_get_report_type_filtered_by_top_level(django_user_client, graphql_user_client):
    response = graphql_user_client(REPORT_TYPES_LIST_GRAPHQL, variables={"topLevelOnly": True})
    content = response.json()
    assert len(content["data"]["allReportTypes"]["edges"]) == 8  # 11 total, with 3 subtypes


def test_user_can_get_report_type_filtered_by_content_type(django_user_client, graphql_user_client):
    other_profile = ProfileFactory()

    response = graphql_user_client(
        REPORT_TYPES_LIST_GRAPHQL, variables={"targetObjectId": other_profile.relay_id}
    )
    content = response.json()
    assert (
        len(content["data"]["allReportTypes"]["edges"]) == 8
    )  # 11 total, with 3 being exclusive to comments
