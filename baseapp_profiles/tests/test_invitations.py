from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.emails import create_invitation
from baseapp_profiles.models import ProfileUserRole
from baseapp_profiles.tests.factories import ProfileFactory


@pytest.mark.django_db
class TestInvitations:
    def test_create_invitation(self):
        owner = UserFactory(email="owner@test.com", first_name="John", last_name="Doe")
        profile = ProfileFactory(owner=owner, name="Test Organization")

        invitation = create_invitation(
            profile=profile,
            inviter=owner,
            invited_email="newmember@test.com",
            role=ProfileUserRole.ProfileRoles.MANAGER
        )

        assert invitation.invited_email == "newmember@test.com"
        assert invitation.role == ProfileUserRole.ProfileRoles.MANAGER
        assert invitation.status == ProfileUserRole.ProfileRoleStatus.PENDING
        assert invitation.invitation_token is not None
        assert len(invitation.invitation_token) == 64
        assert invitation.invited_at is not None
        assert invitation.invitation_expires_at is not None

        days_diff = (invitation.invitation_expires_at - invitation.invited_at).days
        assert days_diff == 15

    def test_invitation_expiration_check(self):
        owner = UserFactory()
        profile = ProfileFactory(owner=owner)

        invitation = create_invitation(
            profile=profile,
            inviter=owner,
            invited_email="test@test.com"
        )

        assert invitation.is_invitation_expired() is False

        invitation.invitation_expires_at = timezone.now() - timedelta(days=1)
        invitation.save()

        assert invitation.is_invitation_expired() is True

    def test_invitation_for_existing_user(self):
        owner = UserFactory()
        profile = ProfileFactory(owner=owner)
        existing_user = UserFactory(email="existing@test.com")

        invitation = create_invitation(
            profile=profile,
            inviter=owner,
            invited_email="existing@test.com"
        )

        assert invitation.user == existing_user
        assert invitation.invited_email == "existing@test.com"

    def test_invitation_for_nonexistent_user(self):
        owner = UserFactory()
        profile = ProfileFactory(owner=owner)

        invitation = create_invitation(
            profile=profile,
            inviter=owner,
            invited_email="nonexistent@test.com"
        )

        assert invitation.user is None
        assert invitation.invited_email == "nonexistent@test.com"

    def test_invitation_token_generation(self):
        owner = UserFactory()
        profile = ProfileFactory(owner=owner)

        invitation = create_invitation(
            profile=profile,
            inviter=owner,
            invited_email="test@test.com"
        )

        old_token = invitation.invitation_token
        invitation.generate_invitation_token()
        invitation.save()

        assert invitation.invitation_token != old_token
        assert len(invitation.invitation_token) == 64


@pytest.mark.django_db
class TestInvitationMutations:
    @patch('baseapp_profiles.emails.send_invitation_email')
    def test_send_profile_invitation_mutation(self, mock_send_email, django_user_client, graphql_user_client):
        profile = ProfileFactory(owner=django_user_client.user)

        mutation = """
            mutation SendInvitation($input: SendProfileInvitationInput!) {
                sendProfileInvitation(input: $input) {
                    profileUserRole {
                        id
                        invitedEmail
                        role
                        status
                    }
                }
            }
        """

        variables = {
            "input": {
                "profileId": profile.relay_id,
                "email": "newmember@test.com",
                "role": "MANAGER"
            }
        }

        response = graphql_user_client(mutation, variables=variables)
        content = response.json()

        if "errors" in content:
            print(f"GraphQL Errors: {content['errors']}")

        assert "data" in content
        assert content["data"]["sendProfileInvitation"]["profileUserRole"]["invitedEmail"] == "newmember@test.com"
        assert content["data"]["sendProfileInvitation"]["profileUserRole"]["status"] == "PENDING"
        assert mock_send_email.called

    def test_accept_profile_invitation_mutation(self, django_user_client, graphql_user_client):
        owner = UserFactory()
        profile = ProfileFactory(owner=owner)

        invitation = create_invitation(
            profile=profile,
            inviter=owner,
            invited_email=django_user_client.user.email,
            role=ProfileUserRole.ProfileRoles.MANAGER
        )

        mutation = """
            mutation AcceptInvitation($input: AcceptProfileInvitationInput!) {
                acceptProfileInvitation(input: $input) {
                    profileUserRole {
                        id
                        status
                    }
                    profile {
                        id
                        name
                    }
                }
            }
        """

        variables = {
            "input": {
                "token": invitation.invitation_token
            }
        }

        response = graphql_user_client(mutation, variables=variables)
        content = response.json()

        assert content["data"]["acceptProfileInvitation"]["profileUserRole"]["status"] == "ACTIVE"
        assert content["data"]["acceptProfileInvitation"]["profile"]["name"] == profile.name

        invitation.refresh_from_db()
        assert invitation.status == ProfileUserRole.ProfileRoleStatus.ACTIVE
        assert invitation.responded_at is not None

    def test_decline_profile_invitation_mutation(self, django_user_client, graphql_user_client):
        owner = UserFactory()
        profile = ProfileFactory(owner=owner)

        invitation = create_invitation(
            profile=profile,
            inviter=owner,
            invited_email=django_user_client.user.email
        )

        mutation = """
            mutation DeclineInvitation($input: DeclineProfileInvitationInput!) {
                declineProfileInvitation(input: $input) {
                    success
                }
            }
        """

        variables = {
            "input": {
                "token": invitation.invitation_token
            }
        }

        response = graphql_user_client(mutation, variables=variables)
        content = response.json()

        assert content["data"]["declineProfileInvitation"]["success"] is True

        invitation.refresh_from_db()
        assert invitation.status == ProfileUserRole.ProfileRoleStatus.DECLINED
        assert invitation.responded_at is not None

    def test_cancel_profile_invitation_mutation(self, django_user_client, graphql_user_client):
        profile = ProfileFactory(owner=django_user_client.user)

        invitation = create_invitation(
            profile=profile,
            inviter=django_user_client.user,
            invited_email="test@test.com"
        )

        mutation = """
            mutation CancelInvitation($input: CancelProfileInvitationInput!) {
                cancelProfileInvitation(input: $input) {
                    success
                }
            }
        """

        variables = {
            "input": {
                "invitationId": invitation.relay_id
            }
        }

        response = graphql_user_client(mutation, variables=variables)
        content = response.json()

        assert content["data"]["cancelProfileInvitation"]["success"] is True

        assert not ProfileUserRole.objects.filter(pk=invitation.pk).exists()
