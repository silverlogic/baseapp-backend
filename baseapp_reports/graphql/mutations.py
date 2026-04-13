import graphene
import swapper
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError
from graphql_relay.connection.arrayconnection import offset_to_cursor

from baseapp_core.graphql import RelayMutation, get_obj_from_relay_id, login_required

from .object_types import ReportsInterface

Report = swapper.load_model("baseapp_reports", "Report")
ReportType = swapper.load_model("baseapp_reports", "ReportType")
ReportObjectType = Report.get_graphql_object_type()

REPORT_SUBJECT_MAX_LENGTH = 250


def get_target_author_profile_id(target):
    """Return the pk of the profile that authored *target*, or ``None``.

    Checks for a ``get_author_profile()`` method on the target (models
    that have author semantics define this).  Falls back to a
    ``profile_id`` FK when present.
    """
    if hasattr(target, "get_author_profile"):
        author_profile = target.get_author_profile()
        return author_profile.pk if author_profile else None

    profile_id = getattr(target, "profile_id", None)
    if profile_id is not None:
        return profile_id

    return None


class ReportCreate(RelayMutation):
    """Create a report against any ``ReportableModel`` target."""

    report = graphene.Field(ReportObjectType._meta.connection.Edge, required=False)
    target = graphene.Field(ReportsInterface)

    class Input:
        target_object_id = graphene.ID(required=True)
        report_type_id = graphene.ID(required=True)
        report_subject = graphene.String(required=False)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        target = get_obj_from_relay_id(info, input.get("target_object_id"))
        report_type = get_obj_from_relay_id(info, input.get("report_type_id"))
        report_subject = input.get("report_subject")

        if not info.context.user.has_perm("baseapp_reports.add_report", target):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        current_profile = info.context.user.current_profile
        is_self_report = False

        if current_profile.relay_id == target.relay_id:
            is_self_report = True
        else:
            author_profile_id = get_target_author_profile_id(target)
            if author_profile_id is not None and author_profile_id == current_profile.pk:
                is_self_report = True

        if is_self_report:
            raise GraphQLError(
                str(_("You cannot report your own content")),
                extensions={"code": "invalid_action"},
            )

        if report_subject and len(report_subject) > REPORT_SUBJECT_MAX_LENGTH:
            raise GraphQLError(
                str(
                    _(
                        "Report subject must be %(max_length)d characters or fewer."
                        % {"max_length": REPORT_SUBJECT_MAX_LENGTH}
                    )
                ),
                extensions={"code": "validation_error"},
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

        return cls(
            report=ReportObjectType._meta.connection.Edge(node=report, cursor=offset_to_cursor(0)),
            target=target,
        )


class ReportsMutations(object):
    report_create = ReportCreate.Field()
