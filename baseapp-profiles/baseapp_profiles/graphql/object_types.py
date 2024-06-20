import django_filters
import graphene
import swapper
from baseapp_auth.graphql import PermissionsInterface
from baseapp_core.graphql import DjangoObjectType
from django.db.models import Q
from graphene import relay

Profile = swapper.load_model("baseapp_profiles", "Profile")


class ProfileInterface(relay.Node):
    profile = graphene.Field(lambda: ProfileObjectType)


class ProfileFilter(django_filters.FilterSet):
    class Meta:
        model = Profile
        fields = ["name"]


class ProfileObjectType(DjangoObjectType):
    target = graphene.Field(lambda: ProfileInterface)

    class Meta:
        interfaces = (relay.Node, PermissionsInterface)
        model = Profile
        fields = ("pk",)
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
