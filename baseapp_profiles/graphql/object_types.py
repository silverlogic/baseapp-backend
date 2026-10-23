from functools import lru_cache
from typing import TYPE_CHECKING

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
from baseapp_profiles.conf import keep_invitation_history
from baseapp_profiles.permissions import active_membership_subquery

from .filters import MemberFilter, ProfileFilter

if TYPE_CHECKING:
    from datetime import datetime

    from django.db.models import QuerySet
    from django.db.models.fields.files import ImageFieldFile

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
profile_app_label = Profile._meta.app_label


def can_view_profile_members(user, profile) -> bool:
    if not user.is_authenticated:
        return False
    return user.has_perm(f"{profile_app_label}.view_profile_members", profile)


def can_view_profile_invitations(user, profile, context=None) -> bool:
    """
    Whether `user` may see `profile`'s invitations: rows that are not memberships (pending,
    declined, expired, cancelled) and every row's invitation details.

    Pass the request as `context` to remember the answer for the rest of the request; it is
    asked once per field of every row in a members list.
    """
    if not user.is_authenticated:
        return False
    cache = None
    if hasattr(context, "__dict__"):
        cache = vars(context).setdefault("_baseapp_profiles_can_view_invitations", {})
        if (user.pk, profile.pk) in cache:
            return cache[(user.pk, profile.pk)]
    allowed = user.has_perm(f"{profile_app_label}.view_profile_invitations", profile)
    if cache is not None:
        cache[(user.pk, profile.pk)] = allowed
    return allowed


def member_statuses() -> list[int]:
    """The statuses shown to someone who may see a profile's members but not its invitations."""
    return [ProfileUserRole.ProfileRoleStatus.ACTIVE, ProfileUserRole.ProfileRoleStatus.INACTIVE]


ProfileRoleTypesEnum = graphene.Enum.from_enum(ProfileUserRole.ProfileRoles)
ProfileRoleStatusTypesEnum = graphene.Enum.from_enum(ProfileUserRole.ProfileRoleStatus)


def is_expired_invitation(role) -> bool:
    """True when a pending invitation has passed its expiration date."""
    return role.status == ProfileUserRole.ProfileRoleStatus.PENDING and role.is_invitation_expired()


@lru_cache(maxsize=1)
def get_profile_metadata_type() -> type[object] | None:
    if not apps.is_installed("baseapp_pages"):
        return None

    from baseapp_pages.graphql.object_types import AbstractMetadataObjectType

    class ProfileMetadata(AbstractMetadataObjectType):
        @property
        def meta_title(self) -> str | None:
            return self.instance.name

        @property
        def meta_description(self) -> None:
            return None

        @property
        def meta_og_type(self) -> str:
            return "profile"

        @property
        def meta_og_image(self) -> "ImageFieldFile":
            return self.instance.image

    return ProfileMetadata


class BaseProfileUserRoleObjectType:
    role = graphene.Field(ProfileRoleTypesEnum)
    status = graphene.Field(ProfileRoleStatusTypesEnum)
    invited_email = graphene.String()
    invited_at = graphene.DateTime()
    invitation_expires_at = graphene.DateTime()
    responded_at = graphene.DateTime()
    is_expired = graphene.Boolean()
    profile = graphene.Field(get_object_type_for_model(Profile))
    invited_first_name = graphene.String()
    invited_last_name = graphene.String()
    message = graphene.String()
    sent_count = graphene.Int()
    last_sent_at = graphene.DateTime()
    deactivated_at = graphene.DateTime()

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
            "invited_first_name",
            "invited_last_name",
            "message",
            "invited_by",
            "sent_count",
            "last_sent_at",
            "deactivated_at",
            "deactivated_by",
        ]
        filterset_class = MemberFilter

    @classmethod
    def _can_view_invitation_fields(cls, info, instance) -> bool:
        return can_view_profile_invitations(info.context.user, instance.profile, info.context)

    def resolve_invited_email(self, info) -> str | None:
        if not BaseProfileUserRoleObjectType._can_view_invitation_fields(info, self):
            return None
        return self.invited_email

    def resolve_invited_at(self, info) -> "datetime | None":
        if not BaseProfileUserRoleObjectType._can_view_invitation_fields(info, self):
            return None
        return self.invited_at

    def resolve_invitation_expires_at(self, info) -> "datetime | None":
        if not BaseProfileUserRoleObjectType._can_view_invitation_fields(info, self):
            return None
        return self.invitation_expires_at

    def resolve_responded_at(self, info) -> "datetime | None":
        if not BaseProfileUserRoleObjectType._can_view_invitation_fields(info, self):
            return None
        return self.responded_at

    # Invitation and audit details are for the profile's members only, like the email above.

    def resolve_invited_first_name(self, info) -> str | None:
        if not BaseProfileUserRoleObjectType._can_view_invitation_fields(info, self):
            return None
        return self.invited_first_name

    def resolve_invited_last_name(self, info) -> str | None:
        if not BaseProfileUserRoleObjectType._can_view_invitation_fields(info, self):
            return None
        return self.invited_last_name

    def resolve_message(self, info) -> str | None:
        if not BaseProfileUserRoleObjectType._can_view_invitation_fields(info, self):
            return None
        return self.message

    def resolve_invited_by(self, info) -> object | None:
        if not BaseProfileUserRoleObjectType._can_view_invitation_fields(info, self):
            return None
        return self.invited_by

    def resolve_sent_count(self, info) -> int | None:
        if not BaseProfileUserRoleObjectType._can_view_invitation_fields(info, self):
            return None
        return self.sent_count

    def resolve_last_sent_at(self, info) -> "datetime | None":
        if not BaseProfileUserRoleObjectType._can_view_invitation_fields(info, self):
            return None
        return self.last_sent_at

    def resolve_deactivated_at(self, info) -> "datetime | None":
        if not BaseProfileUserRoleObjectType._can_view_invitation_fields(info, self):
            return None
        return self.deactivated_at

    def resolve_deactivated_by(self, info) -> object | None:
        if not BaseProfileUserRoleObjectType._can_view_invitation_fields(info, self):
            return None
        return self.deactivated_by

    def resolve_is_expired(self, info) -> bool:
        return is_expired_invitation(self)

    def resolve_profile(self, info) -> "Profile | None":
        # Only expose the org profile while the invitation is still actionable — pending and
        # not yet expired (never for accepted/declined/expired roles).
        is_actionable = (
            self.status == ProfileUserRole.ProfileRoleStatus.PENDING
            and not self.is_invitation_expired()
        )
        return self.profile if is_actionable else None


class ProfileUserRoleObjectType(DjangoObjectType, BaseProfileUserRoleObjectType):
    class Meta(BaseProfileUserRoleObjectType.Meta):
        model = ProfileUserRole

    @classmethod
    def get_node(cls, info, id) -> "ProfileUserRole | None":
        # Relay `node(id: ...)` bypasses every other resolver, so gate it here: only members
        # of the role's profile may fetch a ProfileUserRole by node id.
        node = super().get_node(info, id)
        if node is None:
            return None
        if not can_view_profile_members(info.context.user, node.profile):
            return None
        if node.status not in member_statuses() and not can_view_profile_invitations(
            info.context.user, node.profile, info.context
        ):
            return None
        return node


class ProfileInvitationPreview(graphene.ObjectType):
    """What anyone holding an invitation token may see: enough to greet the invitee."""

    profile_name = graphene.String(required=True)
    invited_email = graphene.String(required=True)
    role = graphene.Field(ProfileRoleTypesEnum, required=True)
    status = graphene.Field(ProfileRoleStatusTypesEnum, required=True)
    expires_at = graphene.DateTime()
    invited_first_name = graphene.String(description="The invitee's first name, if given.")
    invited_last_name = graphene.String(description="The invitee's last name, if given.")
    inviter_name = graphene.String(
        description="Who sent the invitation (full name or email); null when nobody did."
    )
    message = graphene.String(description="The inviter's personal note.")
    profile_image = ThumbnailField(required=False, description="The profile's image.")
    requires_sign_in = graphene.Boolean(
        required=True,
        description="An active account with a password exists for the invited email: the "
        "invitee signs in to accept instead of signing up.",
    )


class ProfileInterface(RelayNode):
    profile = graphene.Field(get_object_type_for_model(Profile))


class ProfilesInterface(RelayNode):
    profiles = DjangoFilterConnectionField(lambda: ProfileObjectType)

    def resolve_profiles(self, info, **kwargs) -> "QuerySet[Profile]":
        if info.context.user.is_authenticated and info.context.user == self:
            # The profiles the user can switch to: their own and those they are an ACTIVE
            # member of. A pending, declined or deactivated membership grants no
            # `use_profile`, so it is not offered.
            return Profile.objects.filter(
                Q(owner_id=info.context.user.id) | active_membership_subquery(info.context.user)
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
    def get_node(cls, info, id) -> "Profile | None":
        node = super().get_node(info, id)
        if not info.context.user.has_perm(f"{profile_app_label}.view_profile", node):
            return None
        return node

    @classmethod
    def pre_optimization_hook(cls, queryset, optimizer) -> "QuerySet[Profile]":
        queryset = super().pre_optimization_hook(queryset, optimizer)
        if service := shared_services.get("commentable_metadata"):
            queryset = service.annotate_queryset(queryset)
        if service := shared_services.get("followable_metadata"):
            queryset = service.annotate_queryset(queryset)
        if service := shared_services.get("reportable_metadata"):
            queryset = service.annotate_queryset(queryset)
        return queryset

    @classmethod
    def get_queryset(cls, queryset, info) -> "QuerySet[Profile]":
        if info.context.user.is_active and info.context.user.is_superuser:
            return queryset

        if not info.context.user.is_authenticated:
            return queryset.filter(status=Profile.ProfileStatus.PUBLIC)
        else:
            # An ownerless private profile is listed for its active members, as the
            # owner's private profile is listed for the owner.
            return queryset.filter(
                Q(status=Profile.ProfileStatus.PUBLIC)
                | Q(owner=info.context.user)
                | Q(active_membership_subquery(info.context.user), owner__isnull=True)
            )

    @classmethod
    def resolve_metadata(cls, instance, info) -> object | None:
        ProfileMetadataType = get_profile_metadata_type()
        if ProfileMetadataType is None:
            return None

        return ProfileMetadataType(instance, info)

    @classmethod
    def resolve_members(cls, instance, info, **kwargs) -> "QuerySet[ProfileUserRole]":
        if not can_view_profile_members(info.context.user, instance):
            return instance.members.none()

        members = instance.members.all()
        if not can_view_profile_invitations(info.context.user, instance, info.context):
            # Someone who may see the members but not the invitations sees the members only.
            members = members.filter(status__in=member_statuses())
        if keep_invitation_history() and kwargs.get("status") is None:
            # With history on a person can have many closed rows; list the people who are
            # members or invited unless the client asks for a status.
            members = members.open()
        return members


class ProfileObjectType(BaseProfileObjectType, DjangoObjectType):
    class Meta(BaseProfileObjectType.Meta):
        model = Profile
