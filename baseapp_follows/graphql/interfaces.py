import graphene
import swapper
from django.contrib.contenttypes.models import ContentType
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.graphql import Node as RelayNode
from baseapp_core.graphql import get_object_type_for_model, get_pk_from_relay_id
from baseapp_core.models import DocumentId

from ..models import FollowStats

Follow = swapper.load_model("baseapp_follows", "Follow")
Profile = swapper.load_model("baseapp_profiles", "Profile")


class FollowsInterface(RelayNode):
    followers = DjangoFilterConnectionField(get_object_type_for_model(Follow))
    following = DjangoFilterConnectionField(get_object_type_for_model(Follow))
    followers_count = graphene.Int()
    following_count = graphene.Int()
    is_followed_by_me = graphene.Boolean(
        profile_id=graphene.ID(required=False),
    )

    def resolve_followers_count(self, info):
        ct = ContentType.objects.get_for_model(self)
        try:
            doc = DocumentId.objects.get(content_type=ct, object_id=self.pk)
            return doc.follow_stats.followers_count
        except (DocumentId.DoesNotExist, FollowStats.DoesNotExist):
            return 0

    def resolve_following_count(self, info):
        ct = ContentType.objects.get_for_model(self)
        try:
            doc = DocumentId.objects.get(content_type=ct, object_id=self.pk)
            return doc.follow_stats.following_count
        except (DocumentId.DoesNotExist, FollowStats.DoesNotExist):
            return 0

    def resolve_followers(self, info, **kwargs):
        ct = ContentType.objects.get_for_model(self)
        return Follow.objects.filter(target__content_type=ct, target__object_id=self.pk)

    def resolve_following(self, info, **kwargs):
        ct = ContentType.objects.get_for_model(self)
        return Follow.objects.filter(actor__content_type=ct, actor__object_id=self.pk)

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
