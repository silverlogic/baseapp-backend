from typing import Any, Optional

import strawberry
import strawberry_django
import swapper
from django.db.models import Model
from django_filters import FilterSet
from strawberry.types import Info

from baseapp_core.plugins import apply_if_installed
from baseapp_core.strawberry import Node, django_type, type_for_model
from baseapp_core.strawberry.enums import enum_from_choices
from baseapp_core.strawberry.filters import GlobalIDFilter

Reaction = swapper.load_model("baseapp_reactions", "Reaction")
ReactionLazyType = type_for_model(Reaction)
ReactionTypesEnum = enum_from_choices(Reaction.ReactionTypes, "ReactionTypes")


class ReactionFilter(FilterSet):
    id = GlobalIDFilter(field_name="id", lookup_expr="exact")

    class Meta:
        model = Reaction
        fields = ["id"]


def _reactions_count_type() -> type:
    names = [reaction_type.name for reaction_type in Reaction.ReactionTypes] + ["total"]
    namespace: dict[str, Any] = {name: None for name in names}
    namespace["__annotations__"] = {name: Optional[int] for name in names}
    return strawberry.type(type("ReactionsCount", (), namespace), name="ReactionsCount")


ReactionsCount = _reactions_count_type()


@strawberry_django.type(Reaction, name="AbstractReaction")
class AbstractReactionType:
    """Reaction fields, shared by the package type and project overrides."""

    created: strawberry.auto
    modified: strawberry.auto
    reaction_type: ReactionTypesEnum | None

    @strawberry_django.field(only=["target_document_id"])
    def target(self, info: Info) -> Node | None:
        return self.target

    @classmethod
    def get_node(cls, info: Info, pk: Any) -> Model | None:
        node = super().get_node(info, pk)
        # Historical: reactions reuse the comments view permission.
        if not info.context.user.has_perm("baseapp_comments.view_comment", node):
            return None
        return node


@django_type(
    Reaction,
    filterset_class=ReactionFilter,
    relations=("user", *apply_if_installed("baseapp_profiles", ["profile"])),
)
class ReactionType(AbstractReactionType, Node):
    pass
