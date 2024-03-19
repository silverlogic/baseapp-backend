import graphene
import swapper
from baseapp_core.graphql import RelayMutation, login_required
from baseapp_core.utils import get_content_type_by_natural_key
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError
from graphql_relay import to_global_id
from graphql_relay.connection.arrayconnection import offset_to_cursor
from graphql_relay.node.node import from_global_id
from baseapp_core.graphql import (
    RelayMutation,
    get_obj_from_relay_id,
    get_pk_from_relay_id,
    login_required,
)

from .object_types import ReportNode, ReportsInterface, ReportTypesEnum

Report = swapper.load_model("baseapp_reports", "Report")


class ReportCreate(RelayMutation):
    report = graphene.Field(ReportNode._meta.connection.Edge, required=False)
    target = graphene.Field(ReportsInterface)

    class Input:
        target_object_id = graphene.ID(required=True)
        report_type = graphene.Field(ReportTypesEnum, required=False)
        report_subject = graphene.String(required=False)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        target = get_obj_from_relay_id(info, input.get("target_object_id"))

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
            defaults={"report_type": report_type},
        )
       
        target.refresh_from_db()

        return ReportCreate(
            reaction=ReportNode._meta.connection.Edge(node=report, cursor=offset_to_cursor(0)),
            target=target,
        )


class ReportsMutations(object):
    reaction_toggle = ReportCreate.Field()
