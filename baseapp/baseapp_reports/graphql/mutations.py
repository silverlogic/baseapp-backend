import graphene
import swapper
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError
from graphql_relay.connection.arrayconnection import offset_to_cursor

from baseapp_core.graphql import RelayMutation, get_obj_from_relay_id, login_required

from .object_types import ReportsInterface, ReportTypesEnum

Report = swapper.load_model("baseapp_reports", "Report")
ReportObjectType = Report.get_graphql_object_type()


class ReportCreate(RelayMutation):
    report = graphene.Field(ReportObjectType._meta.connection.Edge, required=False)
    target = graphene.Field(ReportsInterface)

    class Input:
        target_object_id = graphene.ID(required=True)
        report_type = graphene.Field(ReportTypesEnum, required=False)
        report_subject = graphene.String(required=False)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        target = get_obj_from_relay_id(info, input.get("target_object_id"))
        report_type = input.get("report_type")
        report_subject = input.get("report_subject")

        if not info.context.user.has_perm("baseapp_reports.add_report", target):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        content_type = ContentType.objects.get_for_model(target)

        report = Report.objects.create(
            user=info.context.user,
            target_object_id=target.pk,
            target_content_type=content_type,
            report_type=report_type,
            report_subject=report_subject,
        )

        target.refresh_from_db()

        return ReportCreate(
            report=ReportObjectType._meta.connection.Edge(node=report, cursor=offset_to_cursor(0)),
            target=target,
        )


class ReportsMutations(object):
    report_create = ReportCreate.Field()
