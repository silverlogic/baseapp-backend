import django_filters
import graphene
import swapper
from baseapp_auth.graphql import PermissionsInterface
from baseapp_core.graphql import (
    DjangoObjectType,
    ThumbnailField,
    get_object_type_for_model,
)
from baseapp_pages.meta import AbstractMetadataObjectType
from django.apps import apps
from django.db.models import Q
from graphene import relay

Profile = swapper.load_model("baseapp_profiles", "Profile")


class ProfileInterface(relay.Node):
    profile = graphene.Field(get_object_type_for_model(Profile))


class ProfileFilter(django_filters.FilterSet):
    class Meta:
        model = Profile
        fields = ["name"]


class ProfileMetadata(AbstractMetadataObjectType):
    @property
    def meta_title(self):
        return self.instance.name

    @property
    def meta_description(self):
        return None

    @property
    def meta_og_type(self):
        return "profile"

    @property
    def meta_og_image(self):
        return self.instance.image


interfaces = [relay.Node, PermissionsInterface]
if apps.is_installed("baseapp_pages"):
    from baseapp_pages.graphql import PageInterface

    interfaces.append(PageInterface)


if apps.is_installed("baseapp_follows"):
    from baseapp_follows.graphql.interfaces import FollowsInterface

    interfaces.append(FollowsInterface)


if apps.is_installed("baseapp_blocks"):
    from baseapp_blocks.graphql.object_types import BlocksInterface

    interfaces.append(BlocksInterface)


if apps.is_installed("baseapp_chats"):
    from baseapp_chats.graphql.interfaces import ChatRoomsInterface

    interfaces.append(ChatRoomsInterface)


class BaseProfileObjectType:
    target = graphene.Field(lambda: ProfileInterface)
    image = ThumbnailField(required=False)
    banner_image = ThumbnailField(required=False)

    class Meta:
        interfaces = interfaces
        model = Profile
        fields = "__all__"
        filterset_class = ProfileFilter

    @classmethod
    def get_node(cls, info, id):
        node = super().get_node(info, id)
        if not info.context.user.has_perm("baseapp_profiles.view_profile", node):
            return None
        return node

    @classmethod
    def get_queryset(cls, queryset, info):
        if info.context.user.is_active and info.context.user.is_superuser:
            return queryset

        if not info.context.user.is_authenticated:
            return queryset.filter(status=Profile.ProfileStatus.PUBLIC)
        else:
            return queryset.filter(
                Q(status=Profile.ProfileStatus.PUBLIC) | Q(owner=info.context.user)
            )

    @classmethod
    def resolve_metadata(cls, instance, info):
        return ProfileMetadata(instance, info)


class ProfileObjectType(DjangoObjectType, BaseProfileObjectType):
    class Meta(BaseProfileObjectType.Meta):
        model = Profile
