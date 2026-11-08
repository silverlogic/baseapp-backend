from typing import Any, Optional

import strawberry
import strawberry_django
import swapper
from django.db.models import Model
from strawberry.types import Info

from baseapp_core.plugins import apply_if_installed
from baseapp_core.strawberry import Node, django_type, type_for_model

RateModel = swapper.load_model("baseapp_ratings", "Rate")
RateLazyType = type_for_model(RateModel)


@strawberry_django.type(RateModel, name="AbstractRate")
class AbstractRateType:
    """Rate fields, shared by the package type and project overrides."""

    created: strawberry.auto
    modified: strawberry.auto
    value: strawberry.auto

    @strawberry_django.field(
        graphql_type=Optional[Node],
        only=["target_document_id"],
        prefetch_related=["target_document__content_object"],
    )
    def target(self, info: Info) -> Any:
        target = self.target
        if target is not None and not hasattr(target, "mapped_public_id"):
            # The prefetched DocumentId already holds the relay id: no lookup per row.
            target.mapped_public_id = self.target_document.public_id
        return target

    @classmethod
    def get_node(cls, info: Info, pk: Any) -> Model | None:
        if not info.context.user.has_perm("baseapp_ratings.view_rate"):
            return None
        return super().get_node(info, pk)


@django_type(RateModel, relations=("user", *apply_if_installed("baseapp_profiles", ["profile"])))
class RateType(AbstractRateType, Node):
    pass
