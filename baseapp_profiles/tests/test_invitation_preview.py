"""The fields `profileInvitationPreview` gives the acceptance page."""

from unittest.mock import patch

import pytest
import swapper

from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.services import invitations as service

from .factories import ProfileFactory

pytestmark = pytest.mark.django_db

ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")

PREVIEW = """
    query Preview($token: String!) {
        profileInvitationPreview(token: $token) {
            invitedFirstName
            invitedLastName
            inviterName
            message
            profileImage(width: 48, height: 48)
            requiresSignIn
        }
    }
"""


def preview(graphql_client, invitation) -> dict:
    content = graphql_client(PREVIEW, variables={"token": invitation.invitation_token}).json()
    assert "errors" not in content, content
    return content["data"]["profileInvitationPreview"]


def test_the_invitee_inviter_and_note(graphql_client) -> None:
    inviter = UserFactory(first_name="Olive", last_name="Owner")
    invitation = service.send_invitations(
        ProfileFactory(),
        [{"email": "ann@example.com", "first_name": "Ann", "last_name": "Lee"}],
        invited_by=inviter,
        message="Join us",
    ).invitations[0]

    assert preview(graphql_client, invitation) == {
        "invitedFirstName": "Ann",
        "invitedLastName": "Lee",
        "inviterName": "Olive Owner",
        "message": "Join us",
        "profileImage": None,
        "requiresSignIn": False,
    }


def test_no_inviter(graphql_client) -> None:
    invitation = service.send_invitations(ProfileFactory(), ["ann@example.com"]).invitations[0]

    assert preview(graphql_client, invitation)["inviterName"] is None


@pytest.mark.parametrize(
    "account,requires_sign_in",
    [
        ({}, True),
        ({"is_active": False}, False),
        ({"unusable_password": True}, False),
    ],
)
def test_requires_sign_in(graphql_client, account, requires_sign_in) -> None:
    unusable = account.pop("unusable_password", False)
    user = UserFactory(email="ann@example.com", **account)
    if unusable:
        user.set_unusable_password()
        user.save()
    invitation = service.send_invitations(ProfileFactory(), ["ann@example.com"]).invitations[0]

    assert preview(graphql_client, invitation)["requiresSignIn"] is requires_sign_in


def test_the_profile_image_thumbnail(graphql_client) -> None:
    profile = ProfileFactory()
    invitation = service.send_invitations(profile, ["ann@example.com"]).invitations[0]

    with patch("baseapp_core.graphql.fields.get_thumbnailer") as thumbnailer:
        thumbnailer.return_value.get_thumbnail.return_value.url = "/media/t.jpg"
        profile.image = "profiles/a.jpg"
        profile.save(update_fields=["image"])
        image = preview(graphql_client, invitation)["profileImage"]

    assert image.endswith("/media/t.jpg")
