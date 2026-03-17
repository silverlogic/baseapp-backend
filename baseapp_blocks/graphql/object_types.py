import graphene
import graphene_django_optimizer as gql_optimizer
import swapper
from django.apps import apps
from graphene_django import DjangoConnectionField

from baseapp_core.graphql import DjangoObjectType
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.graphql import get_object_type_for_model, get_pk_from_relay_id

Block = swapper.load_model("baseapp_blocks", "Block")


class BlocksInterface(RelayNode):
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

        if apps.is_installed("baseapp_profiles"):
            return BlocksInterface._resolve_is_blocked_by_me_with_profiles(
                self, info, profile_id=profile_id
            )
        return BlocksInterface._resolve_is_blocked_by_me_without_profiles(self, info)

    @staticmethod
    def _resolve_is_blocked_by_me_with_profiles(root, info, profile_id=None) -> bool:
        Profile = swapper.load_model("baseapp_profiles", "Profile")

        if profile_id:
            pk = get_pk_from_relay_id(profile_id)
            actor = Profile.objects.get_if_member(pk=pk, user=info.context.user)
        else:
            actor = info.context.user.current_profile

        return (
            bool(actor)
            and Block.objects.filter(
                actor_id=actor.id,
                target_id=root.id,
            ).exists()
        )

    @staticmethod
    def _resolve_is_blocked_by_me_without_profiles(root, info) -> bool:
        return Block.objects.filter(
            user_id=info.context.user.id,
            target_id=root.id,
        ).exists()


class BaseBlockObjectType:
    class Meta:
        model = Block
        fields = "__all__"
        interfaces = (RelayNode,)

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
