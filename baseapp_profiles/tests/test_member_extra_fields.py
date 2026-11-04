"""
Project columns on `ProfileUserRole`: `extra_fields` on the services, and mutations a project
subclasses (`ExtensibleMutation`) to accept more input, under the same schema names when
they opt in.

The testproject's concrete model has no project columns, so these tests use the spare
`email` column the abstract model declares.
"""

import graphene
import pytest
import swapper
from django.core.exceptions import FieldDoesNotExist
from django.test import RequestFactory

from baseapp_core.tests.factories import UserFactory
from baseapp_profiles import signals
from baseapp_profiles.exceptions import ProfileMembershipError
from baseapp_profiles.graphql.mutations import (
    ProfileMemberDeactivate,
    ProfileSendInvitation,
    ProfileUserRoleCreate,
    ProfileUserRoleUpdate,
)
from baseapp_profiles.services import invitations as invitation_service
from baseapp_profiles.services import members as member_service

from .factories import ProfileFactory, ProfileUserRoleFactory

pytestmark = pytest.mark.django_db

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
ADMIN = ProfileUserRole.ProfileRoles.ADMIN
MANAGER = ProfileUserRole.ProfileRoles.MANAGER
Status = ProfileUserRole.ProfileRoleStatus


class TestServices:
    def test_send_sets_extra_fields_on_every_row(self) -> None:
        result = invitation_service.send_invitations(
            ProfileFactory(),
            ["ann@example.com", "bob@example.com"],
            extra_fields={"email": "team@example.com"},
        )

        assert {row.email for row in ProfileUserRole.objects.all()} == {"team@example.com"}
        assert len(result.invitations) == 2

    def test_resend_sets_extra_fields(self) -> None:
        invitation = invitation_service.send_invitations(
            ProfileFactory(), ["ann@example.com"]
        ).invitations[0]

        invitation_service.resend_invitation(invitation, extra_fields={"email": "x@example.com"})

        invitation.refresh_from_db()
        assert invitation.email == "x@example.com"

    def test_an_unknown_field_fails_loudly(self) -> None:
        with pytest.raises(FieldDoesNotExist):
            invitation_service.send_invitations(
                ProfileFactory(), ["ann@example.com"], extra_fields={"nope": 1}
            )

    def test_add_members(self, signal_recorder, django_capture_on_commit_callbacks) -> None:
        added = signal_recorder(signals.member_added)
        profile = ProfileFactory()
        ann, bob, by = UserFactory(), UserFactory(), UserFactory()

        with django_capture_on_commit_callbacks(execute=True):
            rows = member_service.add_members(
                profile, [ann, bob, ann], role=ADMIN, by=by, extra_fields={"email": "a@x.com"}
            )

        assert [(row.user, row.role, row.status, row.email) for row in rows] == [
            (ann, ADMIN, Status.ACTIVE, "a@x.com"),
            (bob, ADMIN, Status.ACTIVE, "a@x.com"),
        ]
        assert [(call["instance"].pk, call["by"]) for call in added] == [
            (rows[0].pk, by),
            (rows[1].pk, by),
        ]

    def test_add_members_defaults_to_manager(self) -> None:
        (row,) = member_service.add_members(ProfileFactory(), [UserFactory()])

        assert row.role == MANAGER

    def test_add_members_refuses_the_owner_and_members(self) -> None:
        profile = ProfileFactory()
        member = ProfileUserRoleFactory(profile=profile)

        for users, code in (
            ([UserFactory(), profile.owner], "cannot_add_owner"),
            ([UserFactory(), member.user], "already_member"),
        ):
            with pytest.raises(ProfileMembershipError) as excinfo:
                member_service.add_members(profile, users)
            assert excinfo.value.code == code
        assert ProfileUserRole.objects.count() == 1

    def test_add_members_past_a_closed_invitation_with_history_on(self, settings) -> None:
        settings.BASEAPP_PROFILES_INVITATION_KEEP_HISTORY = True
        declined = ProfileUserRoleFactory(status=Status.DECLINED)

        (row,) = member_service.add_members(declined.profile, [declined.user])

        assert row.pk != declined.pk

    def test_update_member(self, signal_recorder, django_capture_on_commit_callbacks) -> None:
        changed = signal_recorder(signals.member_role_changed)
        member = ProfileUserRoleFactory(role=MANAGER)

        with django_capture_on_commit_callbacks(execute=True):
            member_service.update_member(member, extra_fields={"email": "a@x.com"})
        assert changed == []

        with django_capture_on_commit_callbacks(execute=True):
            member_service.update_member(member, role=ADMIN, extra_fields={"email": "b@x.com"})

        member.refresh_from_db()
        assert (member.role, member.email) == (ADMIN, "b@x.com")
        assert [(call["old_role"], call["new_role"]) for call in changed] == [(MANAGER, ADMIN)]

    def test_deactivate_passes_the_reason_and_saves_extra_fields(
        self, signal_recorder, django_capture_on_commit_callbacks
    ) -> None:
        deactivated = signal_recorder(signals.member_deactivated)
        member = ProfileUserRoleFactory()

        with django_capture_on_commit_callbacks(execute=True):
            member_service.deactivate_member(
                member, reason="Left the company", extra_fields={"email": "old@x.com"}
            )

        member.refresh_from_db()
        assert (member.status, member.email) == (Status.INACTIVE, "old@x.com")
        assert deactivated[0]["reason"] == "Left the company"


# --- A project's mutations ----------------------------------------------------------------


class ProjectSendInvitation(ProfileSendInvitation):
    class Input(ProfileSendInvitation.BaseInput):
        contact_email = graphene.String()

    class Meta:
        keep_type_names = True

    @classmethod
    def extra_fields_from_input(cls, info, input) -> dict:
        return {"email": input.get("contact_email")}


class ProjectUserRoleCreate(ProfileUserRoleCreate):
    class Input(ProfileUserRoleCreate.BaseInput):
        contact_email = graphene.String()

    class Meta:
        keep_type_names = True

    @classmethod
    def extra_fields_from_input(cls, info, input) -> dict:
        return {"email": input.get("contact_email")}


class ProjectUserRoleUpdate(ProfileUserRoleUpdate):
    """Declares no Input: inherits the base one as is."""

    class Meta:
        keep_type_names = True

    @classmethod
    def extra_fields_from_input(cls, info, input) -> dict:
        return {"email": "updated@example.com"}


class ProjectMemberDeactivate(ProfileMemberDeactivate):
    class Input(ProfileMemberDeactivate.BaseInput):
        contact_email = graphene.String()

    class Meta:
        keep_type_names = True

    @classmethod
    def extra_fields_from_input(cls, info, input) -> dict:
        return {"email": input.get("contact_email")}


class Query(graphene.ObjectType):
    ok = graphene.Boolean()


class Mutation(graphene.ObjectType):
    profile_send_invitation = ProjectSendInvitation.Field()
    profile_user_role_create = ProjectUserRoleCreate.Field()
    profile_user_role_update = ProjectUserRoleUpdate.Field()
    profile_member_deactivate = ProjectMemberDeactivate.Field()


@pytest.fixture
def run():
    schema = graphene.Schema(query=Query, mutation=Mutation)

    def execute(user, query: str, variables: dict) -> dict:
        request = RequestFactory().post("/graphql")
        request.user = user
        result = schema.execute(query, variable_values=variables, context_value=request)
        assert result.errors is None, result.errors
        return result.data

    return execute


class TestProjectMutations:
    def test_the_schema_keeps_the_base_names(self) -> None:
        schema = graphene.Schema(query=Query, mutation=Mutation)
        sdl = str(schema)

        assert "input ProfileSendInvitationInput {" in sdl
        assert "type ProfileSendInvitationPayload {" in sdl
        assert "contactEmail: String" in sdl
        # The base input is extended, not replaced.
        assert ProjectSendInvitation.Input._meta.fields.keys() >= {
            "profile_id",
            "emails",
            "invitees",
            "role",
            "message",
            "contact_email",
        }
        assert "role_type" in ProjectUserRoleUpdate.Input._meta.fields

    def test_a_subclass_keeps_its_own_type_names_by_default(self) -> None:
        """A subclass written before `ExtensibleMutation` existed keeps graphene's naming."""

        class OrgMemberCreate(ProfileUserRoleCreate):
            class Input(ProfileUserRoleCreate.BaseInput):
                title = graphene.String()

        class SideBySide(graphene.ObjectType):
            profile_user_role_create = ProfileUserRoleCreate.Field()
            org_member_create = OrgMemberCreate.Field()

        sdl = str(graphene.Schema(query=Query, mutation=SideBySide))

        assert "orgMemberCreate(input: OrgMemberCreateInput!): OrgMemberCreatePayload" in sdl
        assert (
            "profileUserRoleCreate(input: ProfileUserRoleCreateInput!): "
            "ProfileUserRoleCreatePayload"
        ) in sdl
        org_input = sdl[sdl.index("input OrgMemberCreateInput {") :]
        assert "title: String" in org_input[: org_input.index("}")]
        base_input = sdl[sdl.index("input ProfileUserRoleCreateInput {") :]
        assert "title" not in base_input[: base_input.index("}")]

    def test_a_subclass_without_input_keeps_its_own_type_names_by_default(self) -> None:
        class OrgMemberUpdate(ProfileUserRoleUpdate):
            pass

        assert OrgMemberUpdate._meta.name == "OrgMemberUpdatePayload"
        assert OrgMemberUpdate.Input._meta.name == "OrgMemberUpdateInput"

    def test_kept_type_names_carry_down_a_chain_of_subclasses(self) -> None:
        class Further(ProjectSendInvitation):
            class Meta:
                keep_type_names = True

        assert Further._meta.name == "ProfileSendInvitationPayload"
        assert Further.Input._meta.name == "ProfileSendInvitationInput"
        assert "contact_email" in Further.Input._meta.fields

    def test_the_base_mutations_add_no_extra_fields(self) -> None:
        assert ProfileSendInvitation.extra_fields_from_input(None, {"contact_email": "x"}) == {}

    def test_send_stores_the_extra_input(self, run) -> None:
        profile = ProfileFactory()

        run(
            profile.owner,
            """
            mutation Send($input: ProfileSendInvitationInput!) {
                profileSendInvitation(input: $input) { emailsSent }
            }
            """,
            {
                "input": {
                    "profileId": profile.relay_id,
                    "emails": ["ann@example.com"],
                    "role": "MANAGER",
                    "contactEmail": "team@example.com",
                }
            },
        )

        assert ProfileUserRole.objects.get().email == "team@example.com"

    def test_create_update_and_deactivate_store_the_extra_input(self, run) -> None:
        profile = ProfileFactory()
        user = UserFactory()

        data = run(
            profile.owner,
            """
            mutation Create($input: ProfileUserRoleCreateInput!) {
                profileUserRoleCreate(input: $input) { profileUserRoles { id } }
            }
            """,
            {
                "input": {
                    "profileId": profile.relay_id,
                    "usersIds": [user.relay_id],
                    "contactEmail": "created@example.com",
                }
            },
        )
        assert len(data["profileUserRoleCreate"]["profileUserRoles"]) == 1
        member = ProfileUserRole.objects.get(user=user)
        assert member.email == "created@example.com"

        ids = {"profileId": profile.relay_id, "userId": user.relay_id}
        run(
            profile.owner,
            """
            mutation Update($input: ProfileUserRoleUpdateInput!) {
                profileUserRoleUpdate(input: $input) { profileUserRole { id } }
            }
            """,
            {"input": {**ids, "roleType": "ADMIN"}},
        )
        member.refresh_from_db()
        assert (member.role, member.email) == (ADMIN, "updated@example.com")

        run(
            profile.owner,
            """
            mutation Deactivate($input: ProfileMemberDeactivateInput!) {
                profileMemberDeactivate(input: $input) { profileUserRole { id } }
            }
            """,
            {"input": {**ids, "reason": "Left", "contactEmail": "gone@example.com"}},
        )
        member.refresh_from_db()
        assert (member.status, member.email) == (Status.INACTIVE, "gone@example.com")


def test_deactivate_reason_through_the_api(
    django_user_client, graphql_user_client, signal_recorder, django_capture_on_commit_callbacks
) -> None:
    deactivated = signal_recorder(signals.member_deactivated)
    profile = ProfileFactory(owner=django_user_client.user)
    member = ProfileUserRoleFactory(profile=profile)

    with django_capture_on_commit_callbacks(execute=True):
        content = graphql_user_client(
            """
            mutation Deactivate($input: ProfileMemberDeactivateInput!) {
                profileMemberDeactivate(input: $input) { profileUserRole { status } }
            }
            """,
            variables={
                "input": {
                    "profileId": profile.relay_id,
                    "userId": member.user.relay_id,
                    "reason": "Left the company",
                }
            },
        ).json()

    assert content["data"]["profileMemberDeactivate"]["profileUserRole"]["status"] == "INACTIVE"
    assert deactivated[0]["reason"] == "Left the company"
