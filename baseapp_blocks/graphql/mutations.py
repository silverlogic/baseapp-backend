import graphene
import swapper
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError
from graphql_relay import offset_to_cursor

from baseapp_core.graphql import RelayMutation, get_obj_from_relay_id, login_required

from .object_types import BlocksInterface

Block = swapper.load_model("baseapp_blocks", "Block")
BlockObjectType = Block.get_graphql_object_type()


class BlockToggle(RelayMutation):
    block = graphene.Field(BlockObjectType._meta.connection.Edge, required=False)
    target = graphene.Field(BlocksInterface)
    actor = graphene.Field(BlocksInterface)
    block_deleted_id = graphene.ID(required=False)

    class Input:
        actor_object_id = graphene.ID(required=True)
        target_object_id = graphene.ID(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        target = get_obj_from_relay_id(info, input.get("target_object_id"))
        actor = get_obj_from_relay_id(info, input.get("actor_object_id"))

        if not info.context.user.has_perm("baseapp_blocks.add_block_with_profile", actor):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        if not info.context.user.has_perm("baseapp_blocks.add_block", target):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        block, created = Block.objects.get_or_create(
            actor=actor,
            target=target,
            user=info.context.user,
        )

        if not created:
            if not info.context.user.has_perm("baseapp_blocks.delete_block", block):
                raise GraphQLError(
                    str(_("You don't have permission to perform this action")),
                    extensions={"code": "permission_required"},
                )

            block_deleted_id = block.relay_id
            block.delete()
            target.refresh_from_db()
            actor.refresh_from_db()
            return BlockToggle(target=target, actor=actor, block_deleted_id=block_deleted_id)

        target.refresh_from_db()
        actor.refresh_from_db()

        return BlockToggle(
            block=BlockObjectType._meta.connection.Edge(node=block, cursor=offset_to_cursor(0)),
            target=target,
            actor=actor,
        )


class BlocksMutations(object):
    block_toggle = BlockToggle.Field()
