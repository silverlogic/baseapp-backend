import pytest
import swapper
from baseapp_core.tests.factories import UserFactory

Report = swapper.load_model("baseapp_reports", "Report")

pytestmark = pytest.mark.django_db

REPORT_CREATE_GRAPHQL = """
mutation ReportCreate($input: ReportCreateInput!) {
    reportCreate(input: $input) {
        report {
            id
            reportType
            }
        }
    }
"""


def test_anon_cant_report(graphql_client):
    user1 = UserFactory()
    user2 = UserFactory()

    variables = {
        "input": {
            "targetObjectId": user2.relay_id,
            "reportType": "SPAM",
        }
    }

    response = graphql_client(REPORT_CREATE_GRAPHQL, variables=variables)

    content = response.json()
    assert content["errors"][0]["message"] == "authentication required"
    assert Report.objects.count() == 0


def test_user_can_report(django_user_client, graphql_user_client):
    user1 = django_user_client.user
    user2 = UserFactory()

    variables = {
        "input": {
            "targetObjectId": user2.relay_id,
            "reportType": "SPAM",
        }
    }

    response = graphql_user_client(REPORT_CREATE_GRAPHQL, variables=variables)
    content = response.json()
    assert content["data"]["reportCreate"]["report"]["reportType"] == "SPAM"
    assert Report.objects.count() == 1
    