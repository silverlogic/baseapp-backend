from collections.abc import Iterable
from datetime import datetime
from typing import Any, Optional

import strawberry
import strawberry_django
import swapper
from django.db.models import Model, Q, QuerySet
from strawberry.types import Info

from baseapp_auth.strawberry.permissions import PermissionsInterface
from baseapp_core.plugins import strawberry_shared_interfaces
from baseapp_core.strawberry import CountedConnection, Node, django_type, type_for_model
from baseapp_core.strawberry.connections import connection
from baseapp_core.strawberry.enums import choices_enum, enum_from_choices
from baseapp_core.strawberry.fields import thumbnail_field

from ..graphql.filters import MemberFilter, ProfileFilter
from ..graphql.object_types import can_view_profile_members, is_expired_invitation
from .interfaces import ProfileInterface

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
profile_app_label = Profile._meta.app_label

ProfileLazyType = type_for_model(Profile)
ProfileUserRoleLazyType = type_for_model(ProfileUserRole)
ProfileStatusEnum = choices_enum(Profile, "status")
ProfileRolesEnum = enum_from_choices(ProfileUserRole.ProfileRoles, "ProfileRoles")
ProfileRoleStatusEnum = enum_from_choices(ProfileUserRole.ProfileRoleStatus, "ProfileRoleStatus")


def _invitation_field(name: str) -> Any:
    def resolver(root: Model, info: Info) -> Any:
        if not can_view_profile_members(info.context.user, root.profile):
            return None
        return getattr(root, name)

    return resolver


@django_type(
    ProfileUserRole,
    filterset_class=MemberFilter,
    relations=("user",),
    only=["profile_id", "status", "invitation_expires_at"],
)
class ProfileUserRoleType(Node):
    pk: int | None = strawberry_django.field()
    role: ProfileRolesEnum | None
    status: ProfileRoleStatusEnum | None
    invited_email: str | None = strawberry_django.field(resolver=_invitation_field("invited_email"))
    invited_at: datetime | None = strawberry_django.field(resolver=_invitation_field("invited_at"))
    invitation_expires_at: datetime | None = strawberry_django.field(
        resolver=_invitation_field("invitation_expires_at")
    )
    responded_at: datetime | None = strawberry_django.field(
        resolver=_invitation_field("responded_at")
    )

    @strawberry_django.field
    def is_expired(self, info: Info) -> bool | None:
        return is_expired_invitation(self)

    @strawberry.field(graphql_type=Optional[ProfileLazyType])
    def profile(self, info: Info) -> Any:
        # Only expose the org profile while the invitation is still actionable.
        is_actionable = (
            self.status == ProfileUserRole.ProfileRoleStatus.PENDING
            and not self.is_invitation_expired()
        )
        return self.profile if is_actionable else None

    @classmethod
    def get_node(cls, info: Info, pk: Any) -> Model | None:
        node = super().get_node(info, pk)
        if node is None or not can_view_profile_members(info.context.user, node.profile):
            return None
        return node


def profile_interfaces() -> tuple[type, ...]:
    return (
        *strawberry_shared_interfaces.get(
            "ProfileActivityLogInterface",
            "PageInterface",
            "FollowsInterface",
            "ReportsInterface",
            "BlocksInterface",
            "ChatRoomsInterface",
        ),
        PermissionsInterface,
        Node,
    )


@strawberry_django.type(Profile, name="AbstractProfile")
class AbstractProfileType:
    """Profile fields, shared by the package type and project overrides."""

    created: strawberry.auto
    modified: strawberry.auto
    name: strawberry.auto
    biography: strawberry.auto
    target_object_id: strawberry.auto
    status: ProfileStatusEnum
    pk: int | None = strawberry_django.field()
    image: str | None = thumbnail_field("image")
    banner_image: str | None = thumbnail_field("banner_image")

    @strawberry_django.field(
        graphql_type=Optional[ProfileInterface],
        only=["target_content_type_id", "target_object_id"],
    )
    def target(self, info: Info) -> Any:
        return self.target

    @connection(CountedConnection[ProfileUserRoleLazyType] | None, filterset_class=MemberFilter)
    def members(self, info: Info) -> Iterable[Model]:
        if not can_view_profile_members(info.context.user, self):
            return self.members.none()
        return self.members.all()

    @classmethod
    def get_queryset(cls, queryset: QuerySet, info: Info, **kwargs: Any) -> QuerySet:
        user = info.context.user
        if user.is_active and user.is_superuser:
            return queryset
        if not user.is_authenticated:
            return queryset.filter(status=Profile.ProfileStatus.PUBLIC)
        return queryset.filter(Q(status=Profile.ProfileStatus.PUBLIC) | Q(owner=user))

    @classmethod
    def get_node(cls, info: Info, pk: Any) -> Model | None:
        node = super().get_node(info, pk)
        if not info.context.user.has_perm(f"{profile_app_label}.view_profile", node):
            return None
        return node


# Columns read by the permission backends; deferred columns would be refetched per access.
@django_type(
    Profile,
    filterset_class=ProfileFilter,
    relations="__all__",
    only=["status", "owner_id"],
)
class ProfileType(AbstractProfileType, *profile_interfaces()):
    pass
