import graphene
import graphene_django_optimizer as gql_optimizer
import swapper
from graphene import relay
from graphene_django import DjangoConnectionField

from baseapp_core.graphql import (
    DjangoObjectType,
    get_object_type_for_model,
    get_pk_from_relay_id,
)

Block = swapper.load_model("baseapp_blocks", "Block")
Profile = swapper.load_model("baseapp_profiles", "Profile")


class BlocksInterface(relay.Node):
    blockers = DjangoConnectionField(get_object_type_for_model(Block))
    blocking = DjangoConnectionField(get_object_type_for_model(Block))
    blockers_count = graphene.Int()
    blocking_count = graphene.Int()
    is_blocked_by_me = graphene.Boolean(
        profile_id=graphene.ID(required=False),
    )

    def resolve_blockers_count(self, info):
        if info.context.user.has_perm("baseapp_blocks.view_block-blockers_count", self):
            return self.blockers_count

    def resolve_blocking_count(self, info):
        if info.context.user.has_perm("baseapp_blocks.view_block-blocking_count", self):
            return self.blocking_count

    def resolve_blockers(self, info, **kwargs):
        if info.context.user.has_perm("baseapp_blocks.view_block-blockers", self):
            return self.blockers.all()

    def resolve_blocking(self, info, **kwargs):
        if info.context.user.has_perm("baseapp_blocks.view_block-blocking", self):
            return self.blocking.all()
        return Block.objects.none()

    def resolve_is_blocked_by_me(self, info, profile_id=None, **kwargs):
        if not info.context.user.is_authenticated:
            return False
        if profile_id:
            pk = get_pk_from_relay_id(profile_id)
            profile = Profile.objects.get_if_member(pk=pk, user=info.context.user)
        else:
            profile = info.context.user.current_profile
        return (
            profile
            and Block.objects.filter(
                actor_id=profile.id,
                target_id=self.id,
            ).exists()
        )


class BaseBlockObjectType:
    class Meta:
        model = Block
        fields = "__all__"
        interfaces = (relay.Node,)

    @classmethod
    def get_node(self, info, id):
        node = super().get_node(info, id)
        if info.context.user.has_perm("baseapp_blocks.view_block", node):
            return node


class BlockObjectType(
    BaseBlockObjectType, gql_optimizer.OptimizedDjangoObjectType, DjangoObjectType
):
    class Meta(BaseBlockObjectType.Meta):
        pass
