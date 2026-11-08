"""Report / ReportType node contract, exercised on whichever endpoint the tests target."""

import pytest
import swapper
from graphql_relay import to_global_id

from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.tests.factories import ProfileFactory

from .factories import ReportFactory, ReportTypeFactory

Report = swapper.load_model("baseapp_reports", "Report")

pytestmark = pytest.mark.django_db

REPORT_QUERY = """
query Report($id: ID!) {
    report(id: $id) {
        id
        reportSubject
        user { id }
        reportType { key }
        target { id ... on Profile { name } }
    }
}
"""

REPORT_TYPE_QUERY = """
query ReportType($id: ID!) {
    reportTypes(id: $id) {
        key
        label
        parentType { key }
        subTypes { totalCount edges { node { key } } }
    }
}
"""

PROFILE_REPORTS_BY_ID_QUERY = """
query ProfileReports($nodeId: ID!, $reportId: ID) {
    node(id: $nodeId) {
        ... on ReportsInterface {
            reports(id: $reportId) { edges { node { id } } }
        }
    }
}
"""


def test_reporter_can_fetch_own_report_with_target(django_user_client, graphql_user_client) -> None:
    target = ProfileFactory(name="Reported profile")
    report = ReportFactory(user=django_user_client.user, target=target, report_subject="spam")

    content = graphql_user_client(REPORT_QUERY, variables={"id": report.relay_id}).json()

    assert "errors" not in content, content
    node = content["data"]["report"]
    assert node["reportSubject"] == "spam"
    assert node["user"]["id"] == django_user_client.user.relay_id
    assert node["reportType"]["key"] == report.report_type.key
    assert node["target"] == {"id": target.relay_id, "name": "Reported profile"}


def test_other_user_cannot_fetch_report(graphql_user_client) -> None:
    report = ReportFactory(user=UserFactory(), target=ProfileFactory())

    content = graphql_user_client(REPORT_QUERY, variables={"id": report.relay_id}).json()

    assert content["data"]["report"] is None


def test_report_type_exposes_parent_and_sub_types(graphql_client) -> None:
    parent = ReportTypeFactory(key="rt_parent")
    child = ReportTypeFactory(key="rt_child", parent_type=parent)

    parent_content = graphql_client(REPORT_TYPE_QUERY, variables={"id": parent.relay_id}).json()
    child_content = graphql_client(REPORT_TYPE_QUERY, variables={"id": child.relay_id}).json()

    assert "errors" not in parent_content, parent_content
    parent_node = parent_content["data"]["reportTypes"]
    assert parent_node["parentType"] is None
    assert parent_node["subTypes"]["totalCount"] == 1
    assert parent_node["subTypes"]["edges"][0]["node"]["key"] == "rt_child"
    assert child_content["data"]["reportTypes"]["parentType"]["key"] == "rt_parent"


def test_reports_connection_filters_by_report_id(django_user_client, graphql_user_client) -> None:
    django_user_client.user.is_superuser = True
    django_user_client.user.save()
    target = ProfileFactory()
    wanted = ReportFactory(user=UserFactory(), target=target)
    ReportFactory(user=UserFactory(), target=target)

    content = graphql_user_client(
        PROFILE_REPORTS_BY_ID_QUERY,
        variables={"nodeId": target.relay_id, "reportId": to_global_id("Report", wanted.pk)},
    ).json()

    assert "errors" not in content, content
    edges = content["data"]["node"]["reports"]["edges"]
    assert [e["node"]["id"] for e in edges] == [wanted.relay_id]
