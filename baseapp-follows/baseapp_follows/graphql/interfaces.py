import graphene
import swapper
from baseapp_core.graphql import get_pk_from_relay_id
from graphene import relay
from graphene_django.filter import DjangoFilterConnectionField

Follow = swapper.load_model("baseapp_follows", "Follow")


def get_follow_object_type():
    from baseapp_follows.graphql.object_types import FollowObjectType

    return FollowObjectType

    import pdb

    pdb.set_trace()  # TODO: check
    return Follow.GraphQLObjectType  # CAN't do this sadly :/


class FollowsInterface(relay.Node):
    followers = DjangoFilterConnectionField(get_follow_object_type)
    following = DjangoFilterConnectionField(get_follow_object_type)
    followers_count = graphene.Int()
    following_count = graphene.Int()
    is_followed_by_me = graphene.Boolean(
        profile_id=graphene.ID(required=True),
    )

    def resolve_followers_count(self, info):
        return self.followers_count

    def resolve_following_count(self, info):
        return self.following_count

    def resolve_followers(self, info, **kwargs):
        return self.followers.all()

    def resolve_following(self, info, **kwargs):
        return self.following.all()

    def resolve_is_followed_by_me(self, info, profile_id, **kwargs):
        if not info.context.user.is_authenticated:
            return False
        Profile = swapper.load_model("baseapp_profiles", "Profile")
        profile = Profile.objects.get(pk=get_pk_from_relay_id(profile_id))
        return Follow.objects.filter(
            actor_id=profile.id,
            target_id=self.id,
        ).exists()

    # @classmethod
    # def resolve_type(cls, instance, info):
    #     # import pdb; pdb.set_trace()
    #     return instance.GraphQLObjectType
