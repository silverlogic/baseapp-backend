from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy as _
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.graphql import get_object_type_for_model

from ..models import EmailTemplate
from .filters import EmailTemplateFilter

if TYPE_CHECKING:
    from django.db.models import QuerySet


class MessageTemplatesQueries:
    email_templates = DjangoFilterConnectionField(
        get_object_type_for_model(EmailTemplate),
        filterset_class=EmailTemplateFilter,
        description=_(
            "Email templates ordered by name. Empty without the view_emailtemplate permission."
        ),
    )

    def resolve_email_templates(self, info, **kwargs) -> "QuerySet[EmailTemplate]":
        if not info.context.user.has_perm("baseapp_message_templates.view_emailtemplate"):
            return EmailTemplate.objects.none()
        return EmailTemplate.objects.order_by("name")
