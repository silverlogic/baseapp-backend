import strawberry
from strawberry import UNSET

from baseapp_core.strawberry import RelayMutationInput, RelayMutationPayload
from baseapp_core.strawberry.connections import Edge
from baseapp_core.strawberry.mutations import graphene_relay_mutation

from ..graphql import mutations as graphene_mutations
from .types import ProfileLazyType, ProfileRolesEnum, ProfileUserRoleLazyType


@strawberry.input(name="ProfileCreateInput")
class ProfileCreateInput(RelayMutationInput):
    name: str
    owner: str | None = UNSET
    image: str | None = UNSET
    banner_image: str | None = UNSET
    biography: str | None = UNSET
    url_path: str | None = UNSET
    target: str | None = UNSET
    target_content_type: str | None = UNSET
    target_object_id: int | None = UNSET


@strawberry.type(name="ProfileCreatePayload")
class ProfileCreatePayload(RelayMutationPayload):
    profile: Edge[ProfileLazyType] | None = None


@strawberry.input(name="ProfileUpdateInput")
class ProfileUpdateInput(RelayMutationInput):
    id: strawberry.ID
    owner: str | None = UNSET
    name: str | None = UNSET
    image: str | None = UNSET
    banner_image: str | None = UNSET
    biography: str | None = UNSET
    url_path: str | None = UNSET
    phone_number: str | None = UNSET


@strawberry.type(name="ProfileUpdatePayload")
class ProfileUpdatePayload(RelayMutationPayload):
    profile: ProfileLazyType | None = None


@strawberry.input(name="ProfileDeleteInput")
class ProfileDeleteInput(RelayMutationInput):
    id: strawberry.ID


@strawberry.type(name="ProfileDeletePayload")
class ProfileDeletePayload(RelayMutationPayload):
    deleted_id: strawberry.ID | None = None


@strawberry.input(name="ProfileUserRoleCreateInput")
class ProfileUserRoleCreateInput(RelayMutationInput):
    profile_id: strawberry.ID
    users_ids: list[strawberry.ID | None] | None = UNSET
    emails_to_invite: list[str | None] | None = UNSET
    role_type: ProfileRolesEnum | None = None


@strawberry.type(name="ProfileUserRoleCreatePayload")
class ProfileUserRoleCreatePayload(RelayMutationPayload):
    profile_user_roles: list[ProfileUserRoleLazyType | None] | None = None


@strawberry.input(name="ProfileUserRoleUpdateInput")
class ProfileUserRoleUpdateInput(RelayMutationInput):
    profile_id: strawberry.ID
    user_id: strawberry.ID
    role_type: ProfileRolesEnum


@strawberry.type(name="ProfileUserRoleUpdatePayload")
class ProfileUserRoleUpdatePayload(RelayMutationPayload):
    profile_user_role: ProfileUserRoleLazyType | None = None


@strawberry.input(name="ProfileUserRoleDeleteInput")
class ProfileUserRoleDeleteInput(RelayMutationInput):
    profile_id: strawberry.ID
    user_id: strawberry.ID


@strawberry.type(name="ProfileUserRoleDeletePayload")
class ProfileUserRoleDeletePayload(RelayMutationPayload):
    deleted_id: strawberry.ID | None = None


@strawberry.input(name="ProfileSendInvitationInput")
class ProfileSendInvitationInput(RelayMutationInput):
    profile_id: strawberry.ID
    emails: list[str]
    role: ProfileRolesEnum


@strawberry.type(name="ProfileSendInvitationPayload")
class ProfileSendInvitationPayload(RelayMutationPayload):
    profile_user_roles: list[ProfileUserRoleLazyType | None] | None = None
    emails_sent: int | None = None


@strawberry.input(name="ProfileAcceptInvitationInput")
class ProfileAcceptInvitationInput(RelayMutationInput):
    token: str


@strawberry.type(name="ProfileAcceptInvitationPayload")
class ProfileAcceptInvitationPayload(RelayMutationPayload):
    profile_user_role: ProfileUserRoleLazyType | None = None
    profile: ProfileLazyType | None = None


@strawberry.input(name="ProfileDeclineInvitationInput")
class ProfileDeclineInvitationInput(RelayMutationInput):
    token: str


@strawberry.type(name="ProfileDeclineInvitationPayload")
class ProfileDeclineInvitationPayload(RelayMutationPayload):
    success: bool | None = None


@strawberry.input(name="ProfileCancelInvitationInput")
class ProfileCancelInvitationInput(RelayMutationInput):
    invitation_id: strawberry.ID


@strawberry.type(name="ProfileCancelInvitationPayload")
class ProfileCancelInvitationPayload(RelayMutationPayload):
    success: bool | None = None


@strawberry.input(name="ProfileResendInvitationInput")
class ProfileResendInvitationInput(RelayMutationInput):
    invitation_id: strawberry.ID


@strawberry.type(name="ProfileResendInvitationPayload")
class ProfileResendInvitationPayload(RelayMutationPayload):
    profile_user_role: ProfileUserRoleLazyType | None = None
    email_sent: bool | None = None


g = graphene_mutations


@strawberry.type
class ProfilesMutations:
    profile_create = graphene_relay_mutation(
        g.ProfileCreate, ProfileCreateInput, ProfileCreatePayload
    )
    profile_update = graphene_relay_mutation(
        g.ProfileUpdate, ProfileUpdateInput, ProfileUpdatePayload
    )
    profile_delete = graphene_relay_mutation(
        g.ProfileDelete, ProfileDeleteInput, ProfileDeletePayload
    )
    profile_user_role_create = graphene_relay_mutation(
        g.ProfileUserRoleCreate, ProfileUserRoleCreateInput, ProfileUserRoleCreatePayload
    )
    profile_user_role_update = graphene_relay_mutation(
        g.ProfileUserRoleUpdate, ProfileUserRoleUpdateInput, ProfileUserRoleUpdatePayload
    )
    profile_user_role_delete = graphene_relay_mutation(
        g.ProfileUserRoleDelete, ProfileUserRoleDeleteInput, ProfileUserRoleDeletePayload
    )
    profile_send_invitation = graphene_relay_mutation(
        g.ProfileSendInvitation, ProfileSendInvitationInput, ProfileSendInvitationPayload
    )
    profile_accept_invitation = graphene_relay_mutation(
        g.ProfileAcceptInvitation, ProfileAcceptInvitationInput, ProfileAcceptInvitationPayload
    )
    profile_decline_invitation = graphene_relay_mutation(
        g.ProfileDeclineInvitation, ProfileDeclineInvitationInput, ProfileDeclineInvitationPayload
    )
    profile_cancel_invitation = graphene_relay_mutation(
        g.ProfileCancelInvitation, ProfileCancelInvitationInput, ProfileCancelInvitationPayload
    )
    profile_resend_invitation = graphene_relay_mutation(
        g.ProfileResendInvitation, ProfileResendInvitationInput, ProfileResendInvitationPayload
    )
