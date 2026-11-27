"""`BASEAPP_PROFILES_INVITATION_VALIDATOR`: a project may refuse an invitee."""

import pytest
import swapper

from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.exceptions import ProfileMembershipError
from baseapp_profiles.services import invitations as service

from .factories import ProfileFactory

pytestmark = pytest.mark.django_db

ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
Status = ProfileUserRole.ProfileRoleStatus

CALLS = []


def same_domain_only(profile, invitee, invited_by) -> None:
    CALLS.append((profile.pk, invitee.email, getattr(invited_by, "pk", None)))
    if not invitee.email.endswith("@acme.example"):
        raise ProfileMembershipError("Outside the company domain", "outside_domain")


@pytest.fixture(autouse=True)
def reset_calls() -> None:
    CALLS.clear()


@pytest.fixture
def validator(settings) -> None:
    settings.BASEAPP_PROFILES_INVITATION_VALIDATOR = (
        "baseapp_profiles.tests.test_invitation_validator.same_domain_only"
    )


def test_every_invitee_is_accepted_by_default(mailoutbox) -> None:
    result = service.send_invitations(ProfileFactory(), ["ann@elsewhere.example"])

    assert len(result.invitations) == 1
    assert CALLS == []


def test_the_validator_sees_each_invitee(validator) -> None:
    profile = ProfileFactory()
    inviter = UserFactory()

    service.send_invitations(
        profile,
        [{"email": "Ann@Acme.example", "first_name": "Ann"}, "bob@acme.example"],
        invited_by=inviter,
    )

    assert CALLS == [
        (profile.pk, "ann@acme.example", inviter.pk),
        (profile.pk, "bob@acme.example", inviter.pk),
    ]


def test_a_refused_invitee_fails_the_whole_batch(validator, mailoutbox) -> None:
    with pytest.raises(ProfileMembershipError) as excinfo:
        service.send_invitations(ProfileFactory(), ["ann@acme.example", "eve@elsewhere.example"])

    assert excinfo.value.code == "outside_domain"
    assert not ProfileUserRole.objects.exists()
    assert mailoutbox == []


def test_a_resend_that_opens_a_new_row_is_validated(settings, mailoutbox) -> None:
    settings.BASEAPP_PROFILES_INVITATION_KEEP_HISTORY = True
    invitation = service.send_invitations(ProfileFactory(), ["eve@elsewhere.example"]).invitations[
        0
    ]
    invitation.status = Status.EXPIRED
    invitation.save(update_fields=["status"])
    settings.BASEAPP_PROFILES_INVITATION_VALIDATOR = same_domain_only

    with pytest.raises(ProfileMembershipError) as excinfo:
        service.resend_invitation(invitation)

    assert excinfo.value.code == "outside_domain"
    assert ProfileUserRole.objects.count() == 1


def test_graphql_reports_the_validator_code(validator, django_user_client, graphql_user_client):
    profile = ProfileFactory(owner=django_user_client.user)

    content = graphql_user_client(
        """
        mutation Send($input: ProfileSendInvitationInput!) {
            profileSendInvitation(input: $input) { emailsSent }
        }
        """,
        variables={
            "input": {
                "profileId": profile.relay_id,
                "emails": ["eve@elsewhere.example"],
                "role": "MANAGER",
            }
        },
    ).json()

    assert content["errors"][0]["extensions"]["code"] == "outside_domain"
