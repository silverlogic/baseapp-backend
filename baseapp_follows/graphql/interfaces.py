import graphene
import swapper
from query_optimizer import DjangoConnectionField

from baseapp_core.graphql import get_object_type_for_model, get_pk_from_relay_id
from baseapp_core.models import DocumentId
from baseapp_core.plugins import shared_services

Follow = swapper.load_model("baseapp_follows", "Follow")
Profile = swapper.load_model("baseapp_profiles", "Profile")


class FollowsInterface(graphene.Interface):
    followers = DjangoConnectionField(get_object_type_for_model(Follow))
    following = DjangoConnectionField(get_object_type_for_model(Follow))
    followers_count = graphene.Int()
    following_count = graphene.Int()
    is_followed_by_me = graphene.Boolean(
        profile_id=graphene.ID(required=False),
    )

    def resolve_followers_count(self, info):
        if service := shared_services.get("followable_metadata"):
            return service.get_followers_count(self)
        raise RuntimeError("FollowableMetadata service is not available")

    def resolve_following_count(self, info):
        if service := shared_services.get("followable_metadata"):
            return service.get_following_count(self)
        raise RuntimeError("FollowableMetadata service is not available")

    def resolve_followers(self, info, **kwargs):
        doc = DocumentId.get_or_create_for_object(self)
        return Follow.objects.filter(target=doc)

    def resolve_following(self, info, **kwargs):
        doc = DocumentId.get_or_create_for_object(self)
        return Follow.objects.filter(actor=doc)

    def resolve_is_followed_by_me(self, info, profile_id=None, **kwargs):
        if not info.context.user.is_authenticated:
            return False
        if profile_id:
            pk = get_pk_from_relay_id(profile_id)
            profile = Profile.objects.get_if_member(pk=pk, user=info.context.user)
        else:
            profile = info.context.user.current_profile
        if not profile:
            return False
        return Follow.is_following(profile, self)
