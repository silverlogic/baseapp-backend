import graphene
import swapper
from django.apps import apps
from django.db.models import Q
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_auth.graphql import PermissionsInterface
from baseapp_core.graphql import DjangoObjectType
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.graphql import ThumbnailField, get_object_type_for_model
from baseapp_pages.meta import AbstractMetadataObjectType

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
InvitationDeliveryStatusEnum = graphene.Enum.from_enum(ProfileUserRole.InvitationDeliveryStatus)


class BaseProfileUserRoleObjectType:
    role = graphene.Field(ProfileRoleTypesEnum)
    status = graphene.Field(ProfileRoleStatusTypesEnum)
    invited_email = graphene.String()
    invited_at = graphene.DateTime()
    invitation_expires_at = graphene.DateTime()
    responded_at = graphene.DateTime()
    invitation_delivery_status = graphene.Field(InvitationDeliveryStatusEnum)
    invitation_last_sent_at = graphene.DateTime()
    invitation_send_attempts = graphene.Int()
    invitation_last_send_error = graphene.String()

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
            "invitation_delivery_status",
            "invitation_last_sent_at",
            "invitation_send_attempts",
            "invitation_last_send_error",
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

    def resolve_invitation_delivery_status(self, info):
        if not BaseProfileUserRoleObjectType._can_view_invitation_fields(info, self):
            return None
        return self.invitation_delivery_status

    def resolve_invitation_last_sent_at(self, info):
        if not BaseProfileUserRoleObjectType._can_view_invitation_fields(info, self):
            return None
        return self.invitation_last_sent_at

    def resolve_invitation_send_attempts(self, info):
        if not BaseProfileUserRoleObjectType._can_view_invitation_fields(info, self):
            return None
        return self.invitation_send_attempts

    def resolve_invitation_last_send_error(self, info):
        if not BaseProfileUserRoleObjectType._can_view_invitation_fields(info, self):
            return None
        return self.invitation_last_send_error


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


interfaces = [RelayNode, PermissionsInterface]
inheritances = tuple()

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


if apps.is_installed("baseapp.activity_log"):
    from baseapp.activity_log.graphql.interfaces import ProfileActivityLog

    inheritances += (ProfileActivityLog,)

if apps.is_installed("baseapp_reports"):
    from baseapp_reports.graphql.object_types import ReportsInterface

    interfaces.append(ReportsInterface)


class BaseProfileObjectType(*inheritances, object):
    target = graphene.Field(lambda: ProfileInterface)
    image = ThumbnailField(required=False)
    banner_image = ThumbnailField(required=False)
    members = DjangoFilterConnectionField(
        get_object_type_for_model(ProfileUserRole),
    )

    class Meta:
        interfaces = interfaces
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

    @classmethod
    def resolve_members(cls, instance, info, **kwargs):
        if not can_view_profile_members(info.context.user, instance):
            return instance.members.none()

        return instance.members.all()


class ProfileObjectType(DjangoObjectType, BaseProfileObjectType):
    class Meta(BaseProfileObjectType.Meta):
        model = Profile
