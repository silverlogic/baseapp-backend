from collections.abc import Callable, Iterable
from typing import Any

import strawberry
import strawberry_django
import swapper
from django.db.models import Model
from strawberry.types import Info

from baseapp_core.graphql import get_pk_from_relay_id
from baseapp_core.plugins import shared_services
from baseapp_core.strawberry import (
    CountedConnection,
    Node,
    django_type,
    model_from_info,
    type_for_model,
)

Block = swapper.load_model("baseapp_blocks", "Block")
Profile = swapper.load_model("baseapp_profiles", "Profile")

BlockLazyType = type_for_model(Block)
ProfileLazyType = type_for_model(Profile)


def _metadata_annotation(name: str, builder: str) -> dict[str, Callable[[Info], Any]]:
    """Optimizer hint: annotate the count subquery on whatever model implements the interface."""

    def annotation(info: Info) -> Any:
        service = shared_services.get("blockable_metadata")
        return getattr(service, builder)(model_from_info(info))

    return {name: annotation}


@strawberry.interface(name="BlocksInterface")
class BlocksInterface(Node):
    """Blocks fields for any blockable model. Optimizer hints live on the fields themselves."""

    @strawberry_django.connection(CountedConnection[BlockLazyType] | None)
    def blockers(self, info: Info) -> Iterable[Model]:
        if info.context.user.has_perm("baseapp_blocks.view_block-blockers", self):
            return self.blockers.all()
        return Block.objects.none()

    @strawberry_django.connection(CountedConnection[BlockLazyType] | None)
    def blocking(self, info: Info) -> Iterable[Model]:
        if info.context.user.has_perm("baseapp_blocks.view_block-blocking", self):
            return self.blocking.all()
        return Block.objects.none()

    @strawberry_django.field(
        annotate=_metadata_annotation("_blockable_blockers_count", "_blockers_count_subquery")
    )
    def blockers_count(self, info: Info) -> int | None:
        if info.context.user.has_perm("baseapp_blocks.view_block-blockers_count", self):
            return shared_services.get("blockable_metadata").get_blockers_count(self)
        return None

    @strawberry_django.field(
        annotate=_metadata_annotation("_blockable_blocking_count", "_blocking_count_subquery")
    )
    def blocking_count(self, info: Info) -> int | None:
        if info.context.user.has_perm("baseapp_blocks.view_block-blocking_count", self):
            return shared_services.get("blockable_metadata").get_blocking_count(self)
        return None

    @strawberry.field
    def is_blocked_by_me(self, info: Info, profile_id: strawberry.ID | None = None) -> bool | None:
        user = info.context.user
        if not user.is_authenticated:
            return False
        if profile_id:
            actor = Profile.objects.get_if_member(pk=get_pk_from_relay_id(profile_id), user=user)
        else:
            actor = user.current_profile
        return bool(actor) and Block.objects.filter(actor_id=actor.id, target_id=self.id).exists()


# Both FKs point at Profile; strawberry-django only adds the first one when Block is listed
# under a Profile, so the other would be refetched per row.
@django_type(Block, only=["actor_id", "target_id"])
class BlockType(Node):
    actor: ProfileLazyType | None
    target: ProfileLazyType | None
    created: strawberry.auto
    modified: strawberry.auto
    pk: int | None = strawberry_django.field()

    @classmethod
    def get_node(cls, info: Info, pk: Any) -> Model | None:
        node = super().get_node(info, pk)
        if node is not None and info.context.user.has_perm("baseapp_blocks.view_block", node):
            return node
        return None
