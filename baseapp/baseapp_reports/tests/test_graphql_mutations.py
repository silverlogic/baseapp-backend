import pytest
import swapper

from baseapp_profiles.tests.factories import ProfileFactory

from .factories import ReportTypeFactory

Report = swapper.load_model("baseapp_reports", "Report")

pytestmark = pytest.mark.django_db

REPORT_CREATE_GRAPHQL = """
mutation ReportCreate($input: ReportCreateInput!) {
    reportCreate(input: $input) {
        report {
            node {
                id
                created
            }
        }
    }
}
"""


def test_anon_cant_report(graphql_client):
    other_profile = ProfileFactory()
    report_type = ReportTypeFactory()

    variables = {
        "input": {
            "targetObjectId": other_profile.relay_id,
            "reportTypeId": report_type.relay_id,
            "reportSubject": "test",
        }
    }

    response = graphql_client(REPORT_CREATE_GRAPHQL, variables=variables)

    content = response.json()
    assert content["errors"][0]["message"] == "authentication required"
    assert Report.objects.count() == 0


def test_user_can_report(django_user_client, graphql_user_client):
    other_profile = ProfileFactory()
    report_type = ReportTypeFactory()

    variables = {
        "input": {
            "targetObjectId": other_profile.relay_id,
            "reportTypeId": report_type.relay_id,
            "reportSubject": "test",
        }
    }

    response = graphql_user_client(REPORT_CREATE_GRAPHQL, variables=variables)
    content = response.json()
    assert content["data"]["reportCreate"]["report"]["node"]["created"]
    assert Report.objects.count() == 1

    other_profile.refresh_from_db()
    assert other_profile.reports_count["total"] == 1
