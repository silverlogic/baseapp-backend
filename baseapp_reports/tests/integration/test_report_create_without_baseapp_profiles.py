from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import swapper

pytestmark = pytest.mark.django_db


REPORT_CREATE_GRAPHQL = """
mutation ReportCreate($input: ReportCreateInput!) {
  reportCreate(input: $input) {
    report {
      node {
        reportSubject
      }
    }
  }
}
"""

REPORT_TYPES_LIST_GRAPHQL = """
query reportTypesQuery {
  allReportTypes {
    edges {
      node {
        id
        key
      }
    }
  }
}
"""


@pytest.mark.parametrize("with_disabled_apps", [["baseapp_profiles"]], indirect=True)
class TestReportsWithoutBaseappProfiles:
    def test_report_create_uses_user_based_identity_check_without_profiles(
        self, with_disabled_apps, django_user_client, graphql_user_client
    ):
        Report = swapper.load_model("baseapp_reports", "Report")
        ReportType = swapper.load_model("baseapp_reports", "ReportType")
        target = SimpleNamespace(
            pk=25, user_id=77, relay_id="target-relay-id", refresh_from_db=Mock()
        )
        report_type = ReportType(pk=5, key="spam", label="Spam")
        fake_report = Report(
            pk=1,
            user=django_user_client.user,
            report_type=report_type,
            report_subject="spam",
        )
        fake_content_type = object()

        with (
            patch(
                "baseapp_reports.graphql.mutations.get_obj_from_relay_id",
                side_effect=[target, report_type],
            ),
            patch(
                "baseapp_reports.graphql.mutations.ContentType.objects.get_for_model",
                return_value=fake_content_type,
            ),
            patch(
                "baseapp_reports.graphql.mutations.Report.objects.create",
                return_value=fake_report,
            ) as create_report,
        ):
            response = graphql_user_client(
                REPORT_CREATE_GRAPHQL,
                variables={
                    "input": {
                        "targetObjectId": "target-relay-id",
                        "reportTypeId": "report-type-relay-id",
                        "reportSubject": "spam",
                    }
                },
            )
            content = response.json()

        assert "errors" not in content
        assert content["data"]["reportCreate"]["report"]["node"]["reportSubject"] == "spam"
        _, kwargs = create_report.call_args
        assert kwargs["user"] == django_user_client.user
        assert kwargs["target_object_id"] == 25
        assert kwargs["target_content_type"] is fake_content_type
        assert kwargs["report_type"] is report_type
        assert kwargs["report_subject"] == "spam"

    def test_user_cannot_self_report_using_target_user_id_without_profiles(
        self, with_disabled_apps, django_user_client, graphql_user_client
    ):
        user_id = django_user_client.user.id
        target = SimpleNamespace(pk=100, user_id=user_id, relay_id="target-relay-id")
        report_type = SimpleNamespace(pk=5, relay_id="report-type-relay-id")

        with (
            patch(
                "baseapp_reports.graphql.mutations.get_obj_from_relay_id",
                side_effect=[target, report_type],
            ),
            patch("baseapp_reports.graphql.mutations.Report.objects.create") as create_report,
        ):
            response = graphql_user_client(
                REPORT_CREATE_GRAPHQL,
                variables={
                    "input": {
                        "targetObjectId": "target-relay-id",
                        "reportTypeId": "report-type-relay-id",
                        "reportSubject": "self-report",
                    }
                },
            )
            content = response.json()

        assert content["errors"][0]["message"] == "You cannot report yourself"
        create_report.assert_not_called()

    def test_user_cannot_self_report_using_target_pk_without_profiles(
        self, with_disabled_apps, django_user_client, graphql_user_client
    ):
        user_id = django_user_client.user.id
        target = SimpleNamespace(pk=user_id, relay_id="target-relay-id")
        report_type = SimpleNamespace(pk=5, relay_id="report-type-relay-id")

        with (
            patch(
                "baseapp_reports.graphql.mutations.get_obj_from_relay_id",
                side_effect=[target, report_type],
            ),
            patch("baseapp_reports.graphql.mutations.Report.objects.create") as create_report,
        ):
            response = graphql_user_client(
                REPORT_CREATE_GRAPHQL,
                variables={
                    "input": {
                        "targetObjectId": "target-relay-id",
                        "reportTypeId": "report-type-relay-id",
                        "reportSubject": "self-report",
                    }
                },
            )
            content = response.json()

        assert content["errors"][0]["message"] == "You cannot report yourself"
        create_report.assert_not_called()

    def test_query_all_report_types_works_through_graphql_request(
        self, with_disabled_apps, graphql_client
    ):
        ReportType = swapper.load_model("baseapp_reports", "ReportType")
        fake_queryset = ReportType.objects.none()

        with patch(
            "baseapp_reports.graphql.queries.ReportType.objects.all",
            return_value=fake_queryset,
        ):
            response = graphql_client(REPORT_TYPES_LIST_GRAPHQL)
            content = response.json()

        assert "errors" not in content
        edges = content["data"]["allReportTypes"]["edges"]
        assert edges == []
