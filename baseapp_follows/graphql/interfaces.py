import graphene
import swapper
from graphene import relay
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.graphql import get_object_type_for_model, get_pk_from_relay_id

Follow = swapper.load_model("baseapp_follows", "Follow")
Profile = swapper.load_model("baseapp_profiles", "Profile")


class FollowsInterface(relay.Node):
    followers = DjangoFilterConnectionField(get_object_type_for_model(Follow))
    following = DjangoFilterConnectionField(get_object_type_for_model(Follow))
    followers_count = graphene.Int()
    following_count = graphene.Int()
    is_followed_by_me = graphene.Boolean(
        profile_id=graphene.ID(required=False),
    )

    def resolve_followers_count(self, info):
        return self.followers_count

    def resolve_following_count(self, info):
        return self.following_count

    def resolve_followers(self, info, **kwargs):
        return self.followers.all()

    def resolve_following(self, info, **kwargs):
        return self.following.all()

    def resolve_is_followed_by_me(self, info, profile_id=None, **kwargs):
        if not info.context.user.is_authenticated:
            return False
        if profile_id:
            pk = get_pk_from_relay_id(profile_id)
            profile = Profile.objects.get_if_member(pk=pk, user=info.context.user)
        else:
            profile = info.context.user.current_profile
        return (
            profile
            and Follow.objects.filter(
                actor_id=profile.id,
                target_id=self.id,
            ).exists()
        )
