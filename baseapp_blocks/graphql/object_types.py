import graphene
import graphene_django_optimizer as gql_optimizer
import swapper
from query_optimizer import DjangoConnectionField

from baseapp_core.graphql import DjangoObjectType
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.graphql import get_object_type_for_model, get_pk_from_relay_id
from baseapp_core.plugins import shared_services

Block = swapper.load_model("baseapp_blocks", "Block")
Profile = swapper.load_model("baseapp_profiles", "Profile")


# Field-level optimizer hooks below — `query_optimizer` calls them during AST
# compilation only when the matching field is selected, so each attaches its
# subquery annotation to the parent optimizer on demand. The optimizer auto-
# promotes `select_related` to `prefetch_related` when the child sub-optimizer
# has annotations, which is what makes `block.target.blockersCount` resolve
# without an extra DocumentId + BlockableMetadata fetch per row.


def _blockers_count_optimizer_hook(compiler) -> None:
    if service := shared_services.get("blockable_metadata"):
        service.annotate_blockers_count_in_optimizer_compiler(compiler)


def _blocking_count_optimizer_hook(compiler) -> None:
    if service := shared_services.get("blockable_metadata"):
        service.annotate_blocking_count_in_optimizer_compiler(compiler)


class BlocksInterface(RelayNode):
    blockers = DjangoConnectionField(get_object_type_for_model(Block))
    blocking = DjangoConnectionField(get_object_type_for_model(Block))
    blockers_count = graphene.Field(graphene.Int)
    blocking_count = graphene.Field(graphene.Int)
    is_blocked_by_me = graphene.Boolean(
        profile_id=graphene.ID(required=False),
    )
    blockers_count.optimizer_hook = _blockers_count_optimizer_hook
    blocking_count.optimizer_hook = _blocking_count_optimizer_hook

    class Meta:
        # `query_optimizer`'s AST walker skips `... on <Interface>` inline
        # fragments whose declared model doesn't match the queryset's model.
        # Pinning Profile here lets the top-level `node(id: profile-relay-id)`
        # optimization pass descend into BlocksInterface's fields when resolving
        # a Profile. Without this, `block.target.blockersCount` never gets its
        # annotation attached on the outer pass and falls back to a per-row
        # `BlockableMetadata` fetch.
        model = Profile

    def resolve_blockers_count(self, info):
        if info.context.user.has_perm("baseapp_blocks.view_block-blockers_count", self):
            if service := shared_services.get("blockable_metadata"):
                return service.get_blockers_count(self)
            return 0

    def resolve_blocking_count(self, info):
        if info.context.user.has_perm("baseapp_blocks.view_block-blocking_count", self):
            if service := shared_services.get("blockable_metadata"):
                return service.get_blocking_count(self)
            return 0

    def resolve_blockers(self, info, **kwargs):
        if info.context.user.has_perm("baseapp_blocks.view_block-blockers", self):
            return self.blockers.all()
        return Block.objects.none()

    def resolve_blocking(self, info, **kwargs):
        if info.context.user.has_perm("baseapp_blocks.view_block-blocking", self):
            return self.blocking.all()
        return Block.objects.none()

    def resolve_is_blocked_by_me(self, info, profile_id=None, **kwargs):
        if not info.context.user.is_authenticated:
            return False

        if profile_id:
            pk = get_pk_from_relay_id(profile_id)
            actor = Profile.objects.get_if_member(pk=pk, user=info.context.user)
        else:
            actor = info.context.user.current_profile

        return bool(actor) and Block.objects.filter(actor_id=actor.id, target_id=self.id).exists()


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
