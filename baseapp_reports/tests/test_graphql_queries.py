import pytest
import swapper
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

from baseapp_reports.permissions import VIEW_REPORT_PERMISSION

from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.tests.factories import ProfileFactory

from .factories import ReportFactory, ReportTypeFactory

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

PROFILE_REPORTS_QUERY = """
query ProfileReports($nodeId: ID!) {
    node(id: $nodeId) {
        ... on Profile {
            reports(first: 20) {
                totalCount
                edges {
                    node {
                        id
                    }
                }
            }
        }
    }
}
"""

PROFILE_MY_REPORT_QUERY = """
query ProfileMyReport($nodeId: ID!) {
    node(id: $nodeId) {
        ... on Profile {
            myReport {
                id
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


def test_reports_interface_resolve_reports_filters_by_target_profile(
    django_user_client, graphql_user_client
):
    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    target_a = ProfileFactory()
    target_b = ProfileFactory()
    reporter_a = UserFactory()
    reporter_b = UserFactory()
    report_type = ReportTypeFactory()

    report_on_a_first = ReportFactory(user=reporter_a, target=target_a, report_type=report_type)
    report_on_a_second = ReportFactory(user=reporter_b, target=target_a, report_type=report_type)
    ReportFactory(user=reporter_a, target=target_b, report_type=report_type)

    response = graphql_user_client(
        PROFILE_REPORTS_QUERY,
        variables={"nodeId": target_a.relay_id},
    )
    content = response.json()
    assert "errors" not in content, content

    conn = content["data"]["node"]["reports"]
    assert conn["totalCount"] == 2
    assert len(conn["edges"]) == 2
    assert {edge["node"]["id"] for edge in conn["edges"]} == {
        report_on_a_first.relay_id,
        report_on_a_second.relay_id,
    }


def test_reports_interface_resolve_reports_empty_when_no_reports(
    django_user_client, graphql_user_client
):
    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    target = ProfileFactory()

    response = graphql_user_client(
        PROFILE_REPORTS_QUERY,
        variables={"nodeId": target.relay_id},
    )
    content = response.json()
    assert "errors" not in content, content

    conn = content["data"]["node"]["reports"]
    assert conn["totalCount"] == 0
    assert conn["edges"] == []


def test_reports_interface_resolve_reports_anonymous_cannot_list_reports(graphql_client):
    target = ProfileFactory()
    report_type = ReportTypeFactory()
    ReportFactory(user=UserFactory(), target=target, report_type=report_type)

    response = graphql_client(
        PROFILE_REPORTS_QUERY,
        variables={"nodeId": target.relay_id},
    )
    content = response.json()
    assert "errors" not in content, content

    conn = content["data"]["node"]["reports"]
    assert conn["totalCount"] == 0
    assert conn["edges"] == []


def test_reports_interface_resolve_reports_normal_user_without_perm_cannot_list_reports(
    django_user_client, graphql_user_client
):
    django_user_client.user.is_superuser = False
    django_user_client.user.is_staff = False
    django_user_client.user.save()

    target = ProfileFactory()
    report_type = ReportTypeFactory()
    ReportFactory(user=UserFactory(), target=target, report_type=report_type)
    ReportFactory(user=UserFactory(), target=target, report_type=report_type)

    response = graphql_user_client(
        PROFILE_REPORTS_QUERY,
        variables={"nodeId": target.relay_id},
    )
    content = response.json()
    assert "errors" not in content, content

    conn = content["data"]["node"]["reports"]
    assert conn["totalCount"] == 0
    assert conn["edges"] == []


def test_reports_interface_resolve_reports_user_with_view_report_can_list_reports(
    django_user_client, graphql_user_client
):
    user = django_user_client.user
    user.is_superuser = False
    user.is_staff = True
    user.save()

    perm = Permission.objects.get(
        content_type=ContentType.objects.get_for_model(Report),
        codename="view_report",
    )
    assert VIEW_REPORT_PERMISSION == f"{perm.content_type.app_label}.{perm.codename}"
    user.user_permissions.add(perm)
    user.refresh_from_db()
    django_user_client.force_login(user)
    assert user.has_perm(VIEW_REPORT_PERMISSION)

    target = ProfileFactory()
    report_type = ReportTypeFactory()
    r1 = ReportFactory(user=UserFactory(), target=target, report_type=report_type)

    response = graphql_user_client(
        PROFILE_REPORTS_QUERY,
        variables={"nodeId": target.relay_id},
    )
    content = response.json()
    assert "errors" not in content, content

    conn = content["data"]["node"]["reports"]
    assert conn["totalCount"] == 1
    assert conn["edges"][0]["node"]["id"] == r1.relay_id


def test_reports_interface_resolve_my_report_returns_only_current_users_report(
    django_user_client, graphql_user_client
):
    reporter_me = django_user_client.user
    other_user = UserFactory()
    target = ProfileFactory()
    report_type = ReportTypeFactory()

    my_report = ReportFactory(user=reporter_me, target=target, report_type=report_type)
    ReportFactory(user=other_user, target=target, report_type=report_type)

    response = graphql_user_client(
        PROFILE_MY_REPORT_QUERY,
        variables={"nodeId": target.relay_id},
    )
    content = response.json()
    assert "errors" not in content, content

    assert content["data"]["node"]["myReport"]["id"] == my_report.relay_id


def test_reports_interface_resolve_my_report_null_when_user_has_not_reported(
    django_user_client, graphql_user_client
):
    target = ProfileFactory()
    other_user = UserFactory()
    report_type = ReportTypeFactory()
    ReportFactory(user=other_user, target=target, report_type=report_type)

    response = graphql_user_client(
        PROFILE_MY_REPORT_QUERY,
        variables={"nodeId": target.relay_id},
    )
    content = response.json()
    assert "errors" not in content, content
    assert content["data"]["node"]["myReport"] is None


def test_reports_interface_resolve_my_report_null_for_anonymous(graphql_client):
    target = ProfileFactory()
    response = graphql_client(
        PROFILE_MY_REPORT_QUERY,
        variables={"nodeId": target.relay_id},
    )
    content = response.json()
    assert "errors" not in content, content
    assert content["data"]["node"]["myReport"] is None
