import strawberry
import swapper
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError
from graphql_relay import offset_to_cursor
from strawberry.types import Info

from baseapp_core.strawberry import (
    RelayMutationInput,
    RelayMutationPayload,
    relay_mutation,
)
from baseapp_core.strawberry.connections import Edge
from baseapp_core.strawberry.relay import get_instance_from_global_id

from .types import BlockLazyType, BlocksInterface

Block = swapper.load_model("baseapp_blocks", "Block")


def _permission_error() -> GraphQLError:
    return GraphQLError(
        str(_("You don't have permission to perform this action")),
        extensions={"code": "permission_required"},
    )


@strawberry.input(name="BlockToggleInput")
class BlockToggleInput(RelayMutationInput):
    actor_object_id: strawberry.ID
    target_object_id: strawberry.ID


@strawberry.type(name="BlockTogglePayload")
class BlockTogglePayload(RelayMutationPayload):
    block: Edge[BlockLazyType] | None = None
    target: BlocksInterface | None = None
    actor: BlocksInterface | None = None
    block_deleted_id: strawberry.ID | None = None


@strawberry.type
class BlocksMutations:
    @relay_mutation(login_required=True)
    def block_toggle(self, info: Info, input: BlockToggleInput) -> BlockTogglePayload | None:
        user = info.context.user
        target = get_instance_from_global_id(info, input.target_object_id)
        actor = get_instance_from_global_id(info, input.actor_object_id)

        if not user.has_perm("baseapp_blocks.add_block_with_profile", actor):
            raise _permission_error()
        if not user.has_perm("baseapp_blocks.add_block", target):
            raise _permission_error()
        if actor.id == target.id:
            raise GraphQLError(
                str(_("You cannot block yourself")), extensions={"code": "invalid_action"}
            )

        block, created = Block.objects.get_or_create(actor=actor, target=target, user=user)

        if not created:
            if not user.has_perm("baseapp_blocks.delete_block", block):
                raise _permission_error()
            block_deleted_id = block.relay_id
            block.delete()
            target.refresh_from_db()
            actor.refresh_from_db()
            return BlockTogglePayload(target=target, actor=actor, block_deleted_id=block_deleted_id)

        target.refresh_from_db()
        actor.refresh_from_db()
        return BlockTogglePayload(
            block=Edge(node=block, cursor=offset_to_cursor(0)), target=target, actor=actor
        )
