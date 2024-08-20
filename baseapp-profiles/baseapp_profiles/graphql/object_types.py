import django_filters
import graphene
import swapper
from baseapp_auth.graphql import PermissionsInterface
from baseapp_core.graphql import DjangoObjectType, ThumbnailField
from django.apps import apps
from django.db.models import Q
from graphene import relay

Profile = swapper.load_model("baseapp_profiles", "Profile")


class ProfileInterface(relay.Node):
    profile = graphene.Field(lambda: ProfileObjectType)


class ProfileFilter(django_filters.FilterSet):
    class Meta:
        model = Profile
        fields = ["name"]


class ProfileMetadata:
    def __init__(self, instance, info):
        self.instance = instance
        self.info = info

    @property
    def meta_title(self):
        return self.instance.name

    @property
    def meta_description(self):
        return self.instance.name

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


class ProfileObjectType(DjangoObjectType):
    target = graphene.Field(lambda: ProfileInterface)
    image = ThumbnailField(required=False)

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
