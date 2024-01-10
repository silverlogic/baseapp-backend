import django_filters
import graphene
import graphene_django_optimizer as gql_optimizer
import swapper
from baseapp_core.graphql import DjangoObjectType
from django.contrib.contenttypes.models import ContentType
from graphene import relay
from graphene_django.filter import DjangoFilterConnectionField

Follow = swapper.load_model("baseapp_follows", "Follow")


class FollowsFilter(django_filters.FilterSet):
    class Meta:
        model = Follow
        fields = ["target_is_following_back"]


class FollowsInterface(relay.Node):
    followers = DjangoFilterConnectionField(lambda: FollowNode)
    following = DjangoFilterConnectionField(lambda: FollowNode)
    followers_count = graphene.Int()
    following_count = graphene.Int()
    is_followed_by_me = graphene.Boolean()

    def resolve_followers_count(self, info):
        return self.followers_count

    def resolve_following_count(self, info):
        return self.following_count

    def resolve_followers(self, info, **kwargs):
        return self.followers.all()

    def resolve_following(self, info, **kwargs):
        return self.following.all()

    def resolve_is_followed_by_me(self, info, **kwargs):
        if not info.context.user.is_authenticated:
            return False
        return Follow.objects.filter(
            actor_content_type=ContentType.objects.get_for_model(info.context.user),
            actor_object_id=info.context.user.id,
            target_content_type=ContentType.objects.get_for_model(self),
            target_object_id=self.id,
        ).exists()


class FollowNode(gql_optimizer.OptimizedDjangoObjectType, DjangoObjectType):
    target = graphene.Field(relay.Node)
    actor = graphene.Field(relay.Node)

    class Meta:
        model = Follow
        fields = "__all__"
        interfaces = (relay.Node,)
        filterset_class = FollowsFilter
