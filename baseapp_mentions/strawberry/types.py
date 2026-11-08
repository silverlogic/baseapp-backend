import strawberry
import strawberry_django
import swapper

from baseapp_core.strawberry import Node, django_type, type_for_model

Mention = swapper.load_model("baseapp_mentions", "Mention")
MentionLazyType = type_for_model(Mention)


@strawberry_django.type(Mention, name="AbstractMention")
class AbstractMentionType:
    """Mention fields, shared by the package type and project overrides."""

    created: strawberry.auto
    modified: strawberry.auto


@django_type(Mention, relations=("profile",))
class MentionType(AbstractMentionType, Node):
    pass
