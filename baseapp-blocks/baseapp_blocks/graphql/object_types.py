import graphene
import graphene_django_optimizer as gql_optimizer
import swapper
from baseapp_core.graphql import DjangoObjectType
from django.contrib.contenttypes.models import ContentType
from graphene import relay
from graphene_django import DjangoConnectionField

Block = swapper.load_model("baseapp_blocks", "Block")


class BlocksInterface(relay.Node):
    blockers = DjangoConnectionField(lambda: BlockNode)
    blocking = DjangoConnectionField(lambda: BlockNode)
    blockers_count = graphene.Int()
    blocking_count = graphene.Int()
    is_blocked_by_me = graphene.Boolean()

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

    def resolve_is_blocked_by_me(self, info, **kwargs):
        if not info.context.user.is_authenticated:
            return False

        profile = info.context.user.get_venue_or_band()
        return Block.objects.filter(
            actor_content_type=ContentType.objects.get_for_model(profile),
            actor_object_id=profile.id,
            target_content_type=ContentType.objects.get_for_model(self),
            target_object_id=self.id,
        ).exists()


class BlockNode(gql_optimizer.OptimizedDjangoObjectType, DjangoObjectType):
    target = graphene.Field(relay.Node)
    actor = graphene.Field(relay.Node)

    class Meta:
        model = Block
        fields = "__all__"
        interfaces = (relay.Node,)

    @classmethod
    def get_node(self, info, id):
        node = super().get_node(info, id)
        if info.context.user.has_perm("baseapp_blocks.view_block", node):
            return node
