from typing import Any, Optional

import strawberry
import strawberry_django
import swapper
from django.db.models import Model
from graphene_django.filter.utils import get_filterset_class
from strawberry.types import Info

from baseapp_core.plugins import apply_if_installed
from baseapp_core.strawberry import Node, django_type, type_for_model
from baseapp_core.strawberry.enums import enum_from_choices

Reaction = swapper.load_model("baseapp_reactions", "Reaction")
ReactionLazyType = type_for_model(Reaction)
ReactionTypesEnum = enum_from_choices(Reaction.ReactionTypes, "ReactionTypes")

# The FilterSet graphene-django derives from `filter_fields = {"id": ["exact"]}` (global id filter).
ReactionFilter = get_filterset_class(None, model=Reaction, fields={"id": ["exact"]})


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
        # Same permission Graphene's ReactionObjectType.get_node checks.
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
