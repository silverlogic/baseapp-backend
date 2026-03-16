import graphene
import swapper
from django.apps import apps
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.graphql import Node as RelayNode
from baseapp_core.graphql import get_object_type_for_model, get_pk_from_relay_id
from baseapp_core.plugins import apply_if_installed

Follow = swapper.load_model("baseapp_follows", "Follow")


class FollowsInterface(RelayNode):
    followers = DjangoFilterConnectionField(get_object_type_for_model(Follow))
    following = DjangoFilterConnectionField(get_object_type_for_model(Follow))
    followers_count = graphene.Int()
    following_count = graphene.Int()
    is_followed_by_me = graphene.Boolean(
        **apply_if_installed("baseapp_profiles", {"profile_id": graphene.ID(required=False)}),
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
        if apps.is_installed("baseapp_profiles"):
            return self._resolve_is_followed_by_me_with_profiles(info, profile_id=profile_id)
        return self._resolve_is_followed_by_me_with_current_user(info)

    def _resolve_is_followed_by_me_with_profiles(self, info, profile_id=None):
        Profile = swapper.load_model("baseapp_profiles", "Profile")
        if profile_id:
            pk = get_pk_from_relay_id(profile_id)
            actor = Profile.objects.get_if_member(pk=pk, user=info.context.user)
        else:
            actor = info.context.user.current_profile
        return bool(actor) and Follow.objects.filter(actor_id=actor.id, target_id=self.id).exists()

    def _resolve_is_followed_by_me_with_current_user(self, info):
        return Follow.objects.filter(user_id=info.context.user.id, target_id=self.id).exists()
