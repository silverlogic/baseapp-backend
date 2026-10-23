import logging

import graphene
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import gettext_lazy as _
from graphene_django.types import ErrorType
from graphql.error import GraphQLError

from baseapp_core.graphql import RelayMutation, get_obj_from_relay_id, login_required

from ..models import EmailTemplate
from ..registry import get_registered_template, validate_override
from ..services import PreviewError, RateLimitExceeded, send_test_email
from .object_types import GRAPHQL_PART_NAMES, editor_email, overrides_from_arguments

logger = logging.getLogger(__name__)

SUBJECT_MAX_LENGTH = EmailTemplate._meta.get_field("subject").max_length


def _get_template(info: graphene.ResolveInfo, relay_id: str, perm: str) -> EmailTemplate:
    try:
        template = get_obj_from_relay_id(info, relay_id)
    except (ObjectDoesNotExist, AttributeError, TypeError, ValueError):
        template = None
    if not isinstance(template, EmailTemplate):
        raise GraphQLError(str(_("Email template not found.")), extensions={"code": "not_found"})
    if not info.context.user.has_perm(perm, template):
        raise GraphQLError(
            str(_("You don't have permission to perform this action")),
            extensions={"code": "permission_required"},
        )
    return template


def _override_errors(
    template: EmailTemplate, overrides: dict[str, str], recipient: str | None
) -> list[ErrorType]:
    """Field errors for text that cannot be saved on ``template``."""
    registered = get_registered_template(template.name)
    errors = []
    for part, text in overrides.items():
        if registered is None or not registered.is_editable(part):
            messages = [str(_("This part of the email cannot be edited."))]
        else:
            messages = validate_override(template.name, part, text, recipient=recipient)
            if part == "subject" and len(text) > SUBJECT_MAX_LENGTH:
                messages.append(
                    str(_("Use at most %(max)d characters.") % {"max": SUBJECT_MAX_LENGTH})
                )
        if messages:
            errors.append(ErrorType(field=GRAPHQL_PART_NAMES[part], messages=messages))
    return errors


class EmailTemplateUpdate(RelayMutation):
    """Save staff overrides of an email template's editable parts.

    A blank value resets that part to the default copy in the template files.
    """

    email_template = graphene.Field(lambda: EmailTemplate.get_graphql_object_type())

    class Input:
        id = graphene.ID(required=True)
        subject = graphene.String()
        plain_text_content = graphene.String()
        html_content = graphene.String()

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input) -> "EmailTemplateUpdate":
        template = _get_template(
            info, input["id"], "baseapp_message_templates.change_emailtemplate"
        )
        overrides = overrides_from_arguments(input)
        errors = _override_errors(template, overrides, editor_email(info))
        if errors:
            return EmailTemplateUpdate(errors=errors)

        for part, text in overrides.items():
            setattr(template, part, text if text.strip() else "")
        if overrides:
            template.save(update_fields=[*overrides, "modified"])
        return EmailTemplateUpdate(email_template=template)


class EmailTemplateSendTest(RelayMutation):
    """Send a test of an email template, with sample values, to the requesting user only.

    Optional text previews unsaved changes of editable parts, as the editor shows them.
    """

    sent_to = graphene.String(description=_("The address the test was sent to."))

    class Input:
        id = graphene.ID(required=True)
        subject = graphene.String()
        plain_text_content = graphene.String()
        html_content = graphene.String()

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input) -> "EmailTemplateSendTest":
        template = _get_template(
            info, input["id"], "baseapp_message_templates.send_test_emailtemplate"
        )
        user = info.context.user
        if not getattr(user, "email", None):
            raise GraphQLError(
                str(_("Your account has no email address to send the test to.")),
                extensions={"code": "no_email"},
            )
        overrides = overrides_from_arguments(input)
        errors = _override_errors(template, overrides, user.email)
        if errors:
            return EmailTemplateSendTest(errors=errors)

        try:
            sent_to = send_test_email(template, user, overrides)
        except RateLimitExceeded:
            raise GraphQLError(
                str(_("Too many test emails. Try again later.")),
                extensions={"code": "rate_limited"},
            )
        except PreviewError:
            logger.exception("Could not render a test of %r", template.name)
            raise GraphQLError(
                str(_("This email needs real data to preview.")),
                extensions={"code": "preview_failed"},
            )
        return EmailTemplateSendTest(sent_to=sent_to)


class MessageTemplatesMutations:
    email_template_update = EmailTemplateUpdate.Field()
    email_template_send_test = EmailTemplateSendTest.Field()
