from functools import lru_cache

import graphene
import swapper
from django.apps import apps
from django.db.models import Q
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_auth.graphql import PermissionsInterface
from baseapp_core.graphql import DjangoObjectType
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.graphql import ThumbnailField, get_object_type_for_model
from baseapp_core.plugins import graphql_shared_interfaces, shared_services

from .filters import MemberFilter, ProfileFilter

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
profile_app_label = Profile._meta.app_label


def can_view_profile_members(user, profile):
    if not user.is_authenticated:
        return False
    return user.has_perm(f"{profile_app_label}.view_profile_members", profile)


ProfileRoleTypesEnum = graphene.Enum.from_enum(ProfileUserRole.ProfileRoles)
ProfileRoleStatusTypesEnum = graphene.Enum.from_enum(ProfileUserRole.ProfileRoleStatus)


@lru_cache(maxsize=1)
def get_profile_metadata_type() -> type[object] | None:
    if not apps.is_installed("baseapp_pages"):
        return None

    from baseapp_pages.graphql.object_types import AbstractMetadataObjectType

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

    return ProfileMetadata


class BaseProfileUserRoleObjectType:
    role = graphene.Field(ProfileRoleTypesEnum)
    status = graphene.Field(ProfileRoleStatusTypesEnum)
    invited_email = graphene.String()
    invited_at = graphene.DateTime()
    invitation_expires_at = graphene.DateTime()
    responded_at = graphene.DateTime()

    class Meta:
        model = ProfileUserRole
        interfaces = [RelayNode]
        fields = [
            "id",
            "pk",
            "user",
            "role",
            "status",
            "created",
            "modified",
            "invited_email",
            "invited_at",
            "invitation_expires_at",
            "responded_at",
        ]
        filterset_class = MemberFilter

    @classmethod
    def _can_view_invitation_fields(cls, info, instance):
        return can_view_profile_members(info.context.user, instance.profile)

    def resolve_invited_email(self, info):
        if not BaseProfileUserRoleObjectType._can_view_invitation_fields(info, self):
            return None
        return self.invited_email

    def resolve_invited_at(self, info):
        if not BaseProfileUserRoleObjectType._can_view_invitation_fields(info, self):
            return None
        return self.invited_at

    def resolve_invitation_expires_at(self, info):
        if not BaseProfileUserRoleObjectType._can_view_invitation_fields(info, self):
            return None
        return self.invitation_expires_at

    def resolve_responded_at(self, info):
        if not BaseProfileUserRoleObjectType._can_view_invitation_fields(info, self):
            return None
        return self.responded_at


class ProfileUserRoleObjectType(DjangoObjectType, BaseProfileUserRoleObjectType):
    class Meta(BaseProfileUserRoleObjectType.Meta):
        model = ProfileUserRole


class ProfileInterface(RelayNode):
    profile = graphene.Field(get_object_type_for_model(Profile))


class ProfilesInterface(RelayNode):
    profiles = DjangoFilterConnectionField(lambda: ProfileObjectType)

    def resolve_profiles(self, info, **kwargs):
        if info.context.user.is_authenticated and info.context.user == self:
            return Profile.objects.filter(
                Q(owner_id=info.context.user.id) | Q(members__user_id=info.context.user.id)
            ).order_by("name")
        return Profile.objects.none()


class BaseProfileObjectType(object):
    target = graphene.Field(lambda: ProfileInterface)
    image = ThumbnailField(required=False)
    banner_image = ThumbnailField(required=False)
    members = DjangoFilterConnectionField(
        get_object_type_for_model(ProfileUserRole),
    )

    class Meta:
        interfaces = graphql_shared_interfaces.get(
            RelayNode,
            PermissionsInterface,
            "ProfileActivityLogInterface",
            "PageInterface",
            "FollowsInterface",
            "ReportsInterface",
            "BlocksInterface",
            "ChatRoomsInterface",
        )
        model = Profile
        fields = "__all__"
        filterset_class = ProfileFilter

    @classmethod
    def get_node(cls, info, id):
        node = super().get_node(info, id)
        if not info.context.user.has_perm(f"{profile_app_label}.view_profile", node):
            return None
        return node

    @classmethod
    def pre_optimization_hook(cls, queryset, optimizer):
        queryset = super().pre_optimization_hook(queryset, optimizer)
        if service := shared_services.get("commentable_metadata"):
            queryset = service.annotate_queryset(queryset)
        if service := shared_services.get("followable_metadata"):
            queryset = service.annotate_queryset(queryset)
        if service := shared_services.get("reportable_metadata"):
            queryset = service.annotate_queryset(queryset)
        return queryset

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
        ProfileMetadataType = get_profile_metadata_type()
        if ProfileMetadataType is None:
            return None

        return ProfileMetadataType(instance, info)

    @classmethod
    def resolve_members(cls, instance, info, **kwargs):
        if not can_view_profile_members(info.context.user, instance):
            return instance.members.none()

        return instance.members.all()


class ProfileObjectType(BaseProfileObjectType, DjangoObjectType):
    class Meta(BaseProfileObjectType.Meta):
        model = Profile
