import pytest
import swapper

from baseapp_profiles.tests.factories import ProfileFactory
from baseapp_reports.graphql.mutations import REPORT_SUBJECT_MAX_LENGTH

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


def test_user_profile_cant_self_report(django_user_client, graphql_user_client):
    profile = django_user_client.user.profile
    report_type = ReportTypeFactory()

    variables = {
        "input": {
            "targetObjectId": profile.relay_id,
            "reportTypeId": report_type.relay_id,
            "reportSubject": "test",
        }
    }

    response = graphql_user_client(REPORT_CREATE_GRAPHQL, variables=variables)
    content = response.json()

    assert Report.objects.count() == 0

    profile.refresh_from_db()
    assert profile.reports_count["total"] == 0

    assert content["errors"][0]["message"] == "You cannot report your own content"


def test_report_subject_exceeds_max_length(django_user_client, graphql_user_client):
    other_profile = ProfileFactory()
    report_type = ReportTypeFactory()

    long_subject = "x" * (REPORT_SUBJECT_MAX_LENGTH + 1)
    variables = {
        "input": {
            "targetObjectId": other_profile.relay_id,
            "reportTypeId": report_type.relay_id,
            "reportSubject": long_subject,
        }
    }

    response = graphql_user_client(REPORT_CREATE_GRAPHQL, variables=variables)
    content = response.json()

    assert content["errors"][0]["extensions"]["code"] == "validation_error"
    assert "250 characters or fewer" in content["errors"][0]["message"]
    assert Report.objects.count() == 0


def test_report_subject_at_max_length(django_user_client, graphql_user_client):
    other_profile = ProfileFactory()
    report_type = ReportTypeFactory()

    exact_subject = "x" * REPORT_SUBJECT_MAX_LENGTH
    variables = {
        "input": {
            "targetObjectId": other_profile.relay_id,
            "reportTypeId": report_type.relay_id,
            "reportSubject": exact_subject,
        }
    }

    response = graphql_user_client(REPORT_CREATE_GRAPHQL, variables=variables)
    content = response.json()

    assert "errors" not in content
    assert Report.objects.count() == 1
