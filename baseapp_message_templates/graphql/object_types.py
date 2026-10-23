import logging
from typing import Optional

import graphene
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError

from baseapp_core.graphql import DjangoObjectType
from baseapp_core.graphql import Node as RelayNode

from ..models import EmailTemplate
from ..registry import (
    get_default_source,
    get_registered_template,
    is_customized,
    preview_email_template,
    validate_override,
)
from ..services import with_unsaved_text
from .filters import EmailTemplateFilter

logger = logging.getLogger(__name__)

# Model field -> GraphQL field/argument name.
GRAPHQL_PART_NAMES = {
    "subject": "subject",
    "plain_text_content": "plainTextContent",
    "html_content": "htmlContent",
}


class EmailTemplatePlaceholderObjectType(graphene.ObjectType):
    name = graphene.String(required=True, description=_("Dotted name, e.g. order.number."))
    help = graphene.String(required=True)
    sample = graphene.String(required=True, description=_("Value used by previews."))

    class Meta:
        name = "EmailTemplatePlaceholder"

    def resolve_help(self, info) -> str:
        return str(self.help or "")

    def resolve_sample(self, info) -> str:
        return "" if self.sample is None else str(self.sample)


class EmailTemplatePreviewObjectType(graphene.ObjectType):
    subject = graphene.String(required=True)
    body_text = graphene.String(required=True)
    body_html = graphene.String(required=True)

    class Meta:
        name = "EmailTemplatePreview"


def overrides_from_arguments(arguments: dict) -> dict[str, str]:
    """Map GraphQL arguments (snake_case after graphene) to model fields, dropping missing ones."""
    return {
        part: arguments[part]
        for part in GRAPHQL_PART_NAMES
        if part in arguments and arguments[part] is not None
    }


class BaseEmailTemplateObjectType:
    label = graphene.String(required=True, description=_("Registered label, or the name."))
    group = graphene.String(required=True)
    description = graphene.String(required=True)
    is_registered = graphene.Boolean(
        required=True, description=_("Whether code registered this template.")
    )
    editable_fields = graphene.List(
        graphene.NonNull(graphene.String),
        required=True,
        description=_(
            "Parts staff may override: subject, plainTextContent and/or htmlContent. "
            "Empty for templates that are not registered."
        ),
    )
    placeholders = graphene.List(
        graphene.NonNull(EmailTemplatePlaceholderObjectType), required=True
    )
    default_subject = graphene.String(description=_("Raw source of the default subject file."))
    default_plain_text = graphene.String(
        description=_("Raw source of the default plain-text file.")
    )
    is_customized = graphene.Boolean(
        required=True, description=_("Whether an editable part is overridden.")
    )
    preview_subject = graphene.String(
        description=_("The subject rendered with sample values; null when it cannot render.")
    )
    preview = graphene.Field(
        EmailTemplatePreviewObjectType,
        subject=graphene.String(),
        plain_text_content=graphene.String(),
        html_content=graphene.String(),
        description=_(
            "Render with sample values. Arguments preview unsaved text for editable parts; "
            "omitted ones use the saved text, blank ones the default."
        ),
    )

    class Meta:
        interfaces = (RelayNode,)
        model = EmailTemplate
        fields = ("id", "name", "subject", "plain_text_content", "html_content")
        filterset_class = EmailTemplateFilter

    @classmethod
    def get_node(cls, info: graphene.ResolveInfo, id: str) -> Optional[EmailTemplate]:
        node = super().get_node(info, id)
        if node is None or not info.context.user.has_perm(
            "baseapp_message_templates.view_emailtemplate", node
        ):
            return None
        return node

    def resolve_label(self, info) -> str:
        registered = get_registered_template(self.name)
        return str(registered.label) if registered else self.name

    def resolve_group(self, info) -> str:
        registered = get_registered_template(self.name)
        return registered.group if registered else ""

    def resolve_description(self, info) -> str:
        registered = get_registered_template(self.name)
        return str(registered.description or "") if registered else ""

    def resolve_is_registered(self, info) -> bool:
        return self.is_registered

    def resolve_editable_fields(self, info) -> list[str]:
        registered = get_registered_template(self.name)
        if registered is None:
            return []
        return [GRAPHQL_PART_NAMES[part] for part in registered.editable]

    def resolve_placeholders(self, info) -> list:
        registered = get_registered_template(self.name)
        return list(registered.placeholders) if registered else []

    def resolve_default_subject(self, info) -> str | None:
        return get_default_source(self.name, "subject")

    def resolve_default_plain_text(self, info) -> str | None:
        return get_default_source(self.name, "plain_text_content")

    def resolve_is_customized(self, info) -> bool:
        return is_customized(self)

    def resolve_preview_subject(self, info) -> str | None:
        try:
            return preview_email_template(self.name, row=self).subject
        except Exception:
            logger.exception("Could not preview the subject of %r", self.name)
            return None

    def resolve_preview(self, info, **arguments) -> EmailTemplatePreviewObjectType:
        overrides = overrides_from_arguments(arguments)
        for part, text in overrides.items():
            errors = validate_override(self.name, part, text)
            if errors:
                raise GraphQLError(
                    errors[0],
                    extensions={"code": "invalid_template", "field": GRAPHQL_PART_NAMES[part]},
                )
        row, overrides = with_unsaved_text(self, overrides)
        try:
            preview = preview_email_template(
                self.name,
                overrides,
                recipient=getattr(info.context.user, "email", None),
                row=row,
            )
        except Exception:
            logger.exception("Could not preview %r", self.name)
            raise GraphQLError(
                str(_("This email needs real data to preview.")),
                extensions={"code": "preview_failed"},
            )
        return EmailTemplatePreviewObjectType(
            subject=preview.subject, body_text=preview.body_text, body_html=preview.body_html
        )


class EmailTemplateObjectType(BaseEmailTemplateObjectType, DjangoObjectType):
    class Meta:
        interfaces = (RelayNode,)
        model = EmailTemplate
        fields = ("id", "name", "subject", "plain_text_content", "html_content")
        filterset_class = EmailTemplateFilter
