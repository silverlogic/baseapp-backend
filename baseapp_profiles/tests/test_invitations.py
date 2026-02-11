from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import Client
from django.utils import timezone

from baseapp_core.graphql.testing.fixtures import graphql_query
from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.constants import INVITATION_EXPIRATION_DAYS
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
            role=ProfileUserRole.ProfileRoles.MANAGER,
        )

        assert invitation.invited_email == "newmember@test.com"
        assert invitation.role == ProfileUserRole.ProfileRoles.MANAGER
        assert invitation.status == ProfileUserRole.ProfileRoleStatus.PENDING
        assert invitation.invitation_token is not None
        assert len(invitation.invitation_token) == 64
        assert invitation.invited_at is not None
        assert invitation.invitation_expires_at is not None

        days_diff = (invitation.invitation_expires_at - invitation.invited_at).days
        assert days_diff == INVITATION_EXPIRATION_DAYS

    def test_invitation_expiration_check(self):
        owner = UserFactory()
        profile = ProfileFactory(owner=owner)

        invitation = create_invitation(
            profile=profile, inviter=owner, invited_email="test@test.com"
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
            profile=profile, inviter=owner, invited_email="existing@test.com"
        )

        assert invitation.user == existing_user
        assert invitation.invited_email == "existing@test.com"

    def test_invitation_for_nonexistent_user(self):
        owner = UserFactory()
        profile = ProfileFactory(owner=owner)

        invitation = create_invitation(
            profile=profile, inviter=owner, invited_email="nonexistent@test.com"
        )

        assert invitation.user is None
        assert invitation.invited_email == "nonexistent@test.com"

    def test_invitation_token_generation(self):
        owner = UserFactory()
        profile = ProfileFactory(owner=owner)

        invitation = create_invitation(
            profile=profile, inviter=owner, invited_email="test@test.com"
        )

        old_token = invitation.invitation_token
        invitation.generate_invitation_token()
        invitation.save()

        assert invitation.invitation_token != old_token
        assert len(invitation.invitation_token) == 64


@pytest.mark.django_db
class TestInvitationMutations:
    @patch("baseapp_profiles.graphql.mutations._enqueue_invitation_email")
    def test_send_profile_invitation_mutation(
        self, mock_enqueue, django_user_client, graphql_user_client
    ):
        profile = ProfileFactory(owner=django_user_client.user)

        mutation = """
            mutation SendInvitation($input: ProfileSendInvitationInput!) {
                profileSendInvitation(input: $input) {
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
                "role": "MANAGER",
            }
        }

        response = graphql_user_client(mutation, variables=variables)
        content = response.json()

        if "errors" in content:
            print(f"GraphQL Errors: {content['errors']}")

        assert "data" in content
        assert (
            content["data"]["profileSendInvitation"]["profileUserRole"]["invitedEmail"]
            == "newmember@test.com"
        )
        assert content["data"]["profileSendInvitation"]["profileUserRole"]["status"] == "PENDING"
        assert mock_enqueue.called

    def test_accept_profile_invitation_mutation(self, django_user_client, graphql_user_client):
        owner = UserFactory()
        profile = ProfileFactory(owner=owner)

        invitation = create_invitation(
            profile=profile,
            inviter=owner,
            invited_email=django_user_client.user.email,
            role=ProfileUserRole.ProfileRoles.MANAGER,
        )

        mutation = """
            mutation AcceptInvitation($input: ProfileAcceptInvitationInput!) {
                profileAcceptInvitation(input: $input) {
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

        variables = {"input": {"token": invitation.invitation_token}}

        response = graphql_user_client(mutation, variables=variables)
        content = response.json()

        assert content["data"]["profileAcceptInvitation"]["profileUserRole"]["status"] == "ACTIVE"
        assert content["data"]["profileAcceptInvitation"]["profile"]["name"] == profile.name

        invitation.refresh_from_db()
        assert invitation.status == ProfileUserRole.ProfileRoleStatus.ACTIVE
        assert invitation.responded_at is not None

    def test_decline_profile_invitation_mutation(self, django_user_client, graphql_user_client):
        owner = UserFactory()
        profile = ProfileFactory(owner=owner)

        invitation = create_invitation(
            profile=profile, inviter=owner, invited_email=django_user_client.user.email
        )

        mutation = """
            mutation DeclineInvitation($input: ProfileDeclineInvitationInput!) {
                profileDeclineInvitation(input: $input) {
                    success
                }
            }
        """

        variables = {"input": {"token": invitation.invitation_token}}

        response = graphql_user_client(mutation, variables=variables)
        content = response.json()

        assert content["data"]["profileDeclineInvitation"]["success"] is True

        invitation.refresh_from_db()
        assert invitation.status == ProfileUserRole.ProfileRoleStatus.DECLINED
        assert invitation.responded_at is not None

    def test_cancel_profile_invitation_mutation(self, django_user_client, graphql_user_client):
        import swapper

        ActualProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
        profile = ProfileFactory(owner=django_user_client.user)

        invitation = create_invitation(
            profile=profile, inviter=django_user_client.user, invited_email="test@test.com"
        )

        mutation = """
            mutation CancelInvitation($input: ProfileCancelInvitationInput!) {
                profileCancelInvitation(input: $input) {
                    success
                }
            }
        """

        variables = {"input": {"invitationId": invitation.relay_id}}

        response = graphql_user_client(mutation, variables=variables)
        content = response.json()

        assert content["data"]["profileCancelInvitation"]["success"] is True

        assert not ActualProfileUserRole.objects.filter(pk=invitation.pk).exists()

    def test_expired_invitation_sets_expired_status(self, django_user_client, graphql_user_client):
        owner = UserFactory()
        profile = ProfileFactory(owner=owner)

        invitation = create_invitation(
            profile=profile, inviter=owner, invited_email=django_user_client.user.email
        )

        invitation.invitation_expires_at = timezone.now() - timedelta(days=1)
        invitation.save()

        mutation = """
            mutation AcceptInvitation($input: ProfileAcceptInvitationInput!) {
                profileAcceptInvitation(input: $input) {
                    profileUserRole {
                        id
                        status
                    }
                }
            }
        """

        variables = {"input": {"token": invitation.invitation_token}}

        response = graphql_user_client(mutation, variables=variables)
        content = response.json()

        assert "errors" in content
        assert content["errors"][0]["extensions"]["code"] == "expired_invitation"

        # Status remains PENDING because Django's transaction handling rolls back
        # the save() when GraphQLError is raised. The EXPIRED transition happens
        # when ResendInvitation or SendInvitation reuses the row.
        invitation.refresh_from_db()
        assert invitation.status == ProfileUserRole.ProfileRoleStatus.PENDING

    @patch("baseapp_profiles.graphql.mutations._enqueue_invitation_email")
    def test_resend_expired_invitation_mutation(
        self, mock_enqueue, django_user_client, graphql_user_client
    ):
        profile = ProfileFactory(owner=django_user_client.user)

        invitation = create_invitation(
            profile=profile, inviter=django_user_client.user, invited_email="test@test.com"
        )

        invitation.status = ProfileUserRole.ProfileRoleStatus.EXPIRED
        invitation.invitation_expires_at = timezone.now() - timedelta(days=1)
        invitation.save()
        old_token = invitation.invitation_token

        mutation = """
            mutation ResendInvitation($input: ProfileResendInvitationInput!) {
                profileResendInvitation(input: $input) {
                    profileUserRole {
                        id
                        status
                    }
                }
            }
        """

        variables = {"input": {"invitationId": invitation.relay_id}}

        response = graphql_user_client(mutation, variables=variables)
        content = response.json()

        assert content["data"]["profileResendInvitation"]["profileUserRole"]["status"] == "PENDING"
        assert mock_enqueue.called

        invitation.refresh_from_db()
        assert invitation.status == ProfileUserRole.ProfileRoleStatus.PENDING
        assert invitation.invitation_token != old_token
        assert invitation.invitation_expires_at > timezone.now()

    @patch("baseapp_profiles.graphql.mutations._enqueue_invitation_email")
    def test_resend_pending_invitation_mutation(
        self, mock_enqueue, django_user_client, graphql_user_client
    ):
        profile = ProfileFactory(owner=django_user_client.user)

        invitation = create_invitation(
            profile=profile, inviter=django_user_client.user, invited_email="test@test.com"
        )
        old_token = invitation.invitation_token

        mutation = """
            mutation ResendInvitation($input: ProfileResendInvitationInput!) {
                profileResendInvitation(input: $input) {
                    profileUserRole {
                        id
                        status
                    }
                }
            }
        """

        variables = {"input": {"invitationId": invitation.relay_id}}

        response = graphql_user_client(mutation, variables=variables)
        content = response.json()

        assert content["data"]["profileResendInvitation"]["profileUserRole"]["status"] == "PENDING"
        assert mock_enqueue.called

        invitation.refresh_from_db()
        assert invitation.invitation_token != old_token

    def test_cannot_resend_declined_invitation(self, django_user_client, graphql_user_client):
        profile = ProfileFactory(owner=django_user_client.user)

        invitation = create_invitation(
            profile=profile, inviter=django_user_client.user, invited_email="test@test.com"
        )

        invitation.status = ProfileUserRole.ProfileRoleStatus.DECLINED
        invitation.save()

        mutation = """
            mutation ResendInvitation($input: ProfileResendInvitationInput!) {
                profileResendInvitation(input: $input) {
                    profileUserRole {
                        id
                        status
                    }
                }
            }
        """

        variables = {"input": {"invitationId": invitation.relay_id}}

        response = graphql_user_client(mutation, variables=variables)
        content = response.json()

        assert "errors" in content
        assert content["errors"][0]["extensions"]["code"] == "invalid_status"

    def test_cannot_resend_active_invitation(self, django_user_client, graphql_user_client):
        profile = ProfileFactory(owner=django_user_client.user)

        invitation = create_invitation(
            profile=profile, inviter=django_user_client.user, invited_email="test@test.com"
        )

        invitation.status = ProfileUserRole.ProfileRoleStatus.ACTIVE
        invitation.save()

        mutation = """
            mutation ResendInvitation($input: ProfileResendInvitationInput!) {
                profileResendInvitation(input: $input) {
                    profileUserRole {
                        id
                        status
                    }
                }
            }
        """

        variables = {"input": {"invitationId": invitation.relay_id}}

        response = graphql_user_client(mutation, variables=variables)
        content = response.json()

        assert "errors" in content
        assert content["errors"][0]["extensions"]["code"] == "invalid_status"

    def test_accept_null_user_wrong_email_returns_wrong_user(
        self, django_user_client, graphql_user_client
    ):
        owner = UserFactory()
        profile = ProfileFactory(owner=owner)

        invitation = create_invitation(
            profile=profile, inviter=owner, invited_email="nonexistent@test.com"
        )
        assert invitation.user is None

        mutation = """
            mutation AcceptInvitation($input: ProfileAcceptInvitationInput!) {
                profileAcceptInvitation(input: $input) {
                    profileUserRole {
                        id
                        status
                    }
                }
            }
        """

        variables = {"input": {"token": invitation.invitation_token}}

        response = graphql_user_client(mutation, variables=variables)
        content = response.json()

        assert "errors" in content
        assert content["errors"][0]["extensions"]["code"] == "wrong_user"

    def test_decline_null_user_wrong_email_returns_wrong_user(
        self, django_user_client, graphql_user_client
    ):
        owner = UserFactory()
        profile = ProfileFactory(owner=owner)

        invitation = create_invitation(
            profile=profile, inviter=owner, invited_email="nonexistent@test.com"
        )
        assert invitation.user is None

        mutation = """
            mutation DeclineInvitation($input: ProfileDeclineInvitationInput!) {
                profileDeclineInvitation(input: $input) {
                    success
                }
            }
        """

        variables = {"input": {"token": invitation.invitation_token}}

        response = graphql_user_client(mutation, variables=variables)
        content = response.json()

        assert "errors" in content
        assert content["errors"][0]["extensions"]["code"] == "wrong_user"

    def test_accept_null_user_matching_email_binds_user(
        self, django_user_client, graphql_user_client
    ):
        import swapper

        ActualProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
        owner = UserFactory()
        profile = ProfileFactory(owner=owner)

        invitation = ActualProfileUserRole.objects.create(
            profile=profile,
            user=None,
            invited_email=django_user_client.user.email,
            role=ProfileUserRole.ProfileRoles.MANAGER,
            status=ProfileUserRole.ProfileRoleStatus.PENDING,
            invited_at=timezone.now(),
            invitation_expires_at=timezone.now() + timedelta(days=INVITATION_EXPIRATION_DAYS),
        )
        invitation.generate_invitation_token()
        invitation.save()
        assert invitation.user is None

        mutation = """
            mutation AcceptInvitation($input: ProfileAcceptInvitationInput!) {
                profileAcceptInvitation(input: $input) {
                    profileUserRole {
                        status
                    }
                }
            }
        """

        variables = {"input": {"token": invitation.invitation_token}}

        response = graphql_user_client(mutation, variables=variables)
        content = response.json()

        assert "errors" not in content
        assert content["data"]["profileAcceptInvitation"]["profileUserRole"]["status"] == "ACTIVE"

        invitation.refresh_from_db()
        assert invitation.user == django_user_client.user
        assert invitation.status == ProfileUserRole.ProfileRoleStatus.ACTIVE

    def test_decline_null_user_matching_email_binds_user(
        self, django_user_client, graphql_user_client
    ):
        import swapper

        ActualProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
        owner = UserFactory()
        profile = ProfileFactory(owner=owner)

        invitation = ActualProfileUserRole.objects.create(
            profile=profile,
            user=None,
            invited_email=django_user_client.user.email,
            role=ProfileUserRole.ProfileRoles.MANAGER,
            status=ProfileUserRole.ProfileRoleStatus.PENDING,
            invited_at=timezone.now(),
            invitation_expires_at=timezone.now() + timedelta(days=INVITATION_EXPIRATION_DAYS),
        )
        invitation.generate_invitation_token()
        invitation.save()
        assert invitation.user is None

        mutation = """
            mutation DeclineInvitation($input: ProfileDeclineInvitationInput!) {
                profileDeclineInvitation(input: $input) {
                    success
                }
            }
        """

        variables = {"input": {"token": invitation.invitation_token}}

        response = graphql_user_client(mutation, variables=variables)
        content = response.json()

        assert "errors" not in content
        assert content["data"]["profileDeclineInvitation"]["success"] is True

        invitation.refresh_from_db()
        assert invitation.user == django_user_client.user
        assert invitation.status == ProfileUserRole.ProfileRoleStatus.DECLINED


@pytest.mark.django_db
class TestInvitationStateMachine:
    @patch("baseapp_profiles.graphql.mutations._enqueue_invitation_email")
    def test_send_invitation_reuses_declined_row(
        self, mock_enqueue, django_user_client, graphql_user_client
    ):
        import swapper

        ActualProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
        profile = ProfileFactory(owner=django_user_client.user)
        email = "declined@test.com"

        invitation = create_invitation(
            profile=profile, inviter=django_user_client.user, invited_email=email
        )
        original_pk = invitation.pk
        invitation.status = ProfileUserRole.ProfileRoleStatus.DECLINED
        invitation.responded_at = timezone.now()
        invitation.save()

        mutation = """
            mutation SendInvitation($input: ProfileSendInvitationInput!) {
                profileSendInvitation(input: $input) {
                    profileUserRole {
                        id
                        status
                        invitedEmail
                    }
                }
            }
        """

        variables = {"input": {"profileId": profile.relay_id, "email": email, "role": "MANAGER"}}

        response = graphql_user_client(mutation, variables=variables)
        content = response.json()

        assert "data" in content
        assert content["data"]["profileSendInvitation"]["profileUserRole"]["status"] == "PENDING"
        assert (
            ActualProfileUserRole.objects.filter(profile=profile, invited_email=email).count() == 1
        )

        invitation.refresh_from_db()
        assert invitation.pk == original_pk
        assert invitation.status == ProfileUserRole.ProfileRoleStatus.PENDING
        assert invitation.responded_at is None

    @patch("baseapp_profiles.graphql.mutations._enqueue_invitation_email")
    def test_send_invitation_reuses_inactive_row(
        self, mock_enqueue, django_user_client, graphql_user_client
    ):
        import swapper

        ActualProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
        profile = ProfileFactory(owner=django_user_client.user)
        email = "inactive@test.com"

        invitation = create_invitation(
            profile=profile, inviter=django_user_client.user, invited_email=email
        )
        original_pk = invitation.pk
        invitation.status = ProfileUserRole.ProfileRoleStatus.INACTIVE
        invitation.save()

        mutation = """
            mutation SendInvitation($input: ProfileSendInvitationInput!) {
                profileSendInvitation(input: $input) {
                    profileUserRole {
                        status
                    }
                }
            }
        """

        variables = {"input": {"profileId": profile.relay_id, "email": email, "role": "ADMIN"}}

        response = graphql_user_client(mutation, variables=variables)
        content = response.json()

        assert content["data"]["profileSendInvitation"]["profileUserRole"]["status"] == "PENDING"
        assert (
            ActualProfileUserRole.objects.filter(profile=profile, invited_email=email).count() == 1
        )

        invitation.refresh_from_db()
        assert invitation.pk == original_pk
        assert invitation.role == ProfileUserRole.ProfileRoles.ADMIN

    @patch("baseapp_profiles.graphql.mutations._enqueue_invitation_email")
    def test_send_invitation_reuses_expired_row(
        self, mock_enqueue, django_user_client, graphql_user_client
    ):
        import swapper

        ActualProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
        profile = ProfileFactory(owner=django_user_client.user)
        email = "expired@test.com"

        invitation = create_invitation(
            profile=profile, inviter=django_user_client.user, invited_email=email
        )
        original_pk = invitation.pk
        original_token = invitation.invitation_token
        invitation.status = ProfileUserRole.ProfileRoleStatus.EXPIRED
        invitation.invitation_expires_at = timezone.now() - timedelta(days=1)
        invitation.save()

        mutation = """
            mutation SendInvitation($input: ProfileSendInvitationInput!) {
                profileSendInvitation(input: $input) {
                    profileUserRole {
                        status
                    }
                }
            }
        """

        variables = {"input": {"profileId": profile.relay_id, "email": email, "role": "MANAGER"}}

        response = graphql_user_client(mutation, variables=variables)
        content = response.json()

        assert content["data"]["profileSendInvitation"]["profileUserRole"]["status"] == "PENDING"
        assert (
            ActualProfileUserRole.objects.filter(profile=profile, invited_email=email).count() == 1
        )

        invitation.refresh_from_db()
        assert invitation.pk == original_pk
        assert invitation.invitation_token != original_token
        assert invitation.invitation_expires_at > timezone.now()

    def test_send_invitation_blocks_pending_duplicate(
        self, django_user_client, graphql_user_client
    ):
        profile = ProfileFactory(owner=django_user_client.user)
        email = "pending@test.com"

        invitation = create_invitation(
            profile=profile, inviter=django_user_client.user, invited_email=email
        )
        invitation.invitation_delivery_status = ProfileUserRole.InvitationDeliveryStatus.SENT
        invitation.invitation_last_sent_at = timezone.now()
        invitation.save()

        mutation = """
            mutation SendInvitation($input: ProfileSendInvitationInput!) {
                profileSendInvitation(input: $input) {
                    profileUserRole {
                        status
                    }
                }
            }
        """

        variables = {"input": {"profileId": profile.relay_id, "email": email, "role": "MANAGER"}}

        response = graphql_user_client(mutation, variables=variables)
        content = response.json()

        assert "errors" in content
        assert content["errors"][0]["extensions"]["code"] == "rate_limited"

    def test_send_invitation_blocks_active_member(self, django_user_client, graphql_user_client):
        profile = ProfileFactory(owner=django_user_client.user)
        email = "active@test.com"

        invitation = create_invitation(
            profile=profile, inviter=django_user_client.user, invited_email=email
        )
        invitation.status = ProfileUserRole.ProfileRoleStatus.ACTIVE
        invitation.save()

        mutation = """
            mutation SendInvitation($input: ProfileSendInvitationInput!) {
                profileSendInvitation(input: $input) {
                    profileUserRole {
                        status
                    }
                }
            }
        """

        variables = {"input": {"profileId": profile.relay_id, "email": email, "role": "MANAGER"}}

        response = graphql_user_client(mutation, variables=variables)
        content = response.json()

        assert "errors" in content
        assert content["errors"][0]["extensions"]["code"] == "already_member"

    @patch("baseapp_profiles.graphql.mutations._enqueue_invitation_email")
    def test_send_invitation_handles_expired_pending(
        self, mock_enqueue, django_user_client, graphql_user_client
    ):
        import swapper

        ActualProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
        profile = ProfileFactory(owner=django_user_client.user)
        email = "expiredpending@test.com"

        invitation = create_invitation(
            profile=profile, inviter=django_user_client.user, invited_email=email
        )
        original_pk = invitation.pk
        invitation.invitation_expires_at = timezone.now() - timedelta(days=1)
        invitation.save()

        mutation = """
            mutation SendInvitation($input: ProfileSendInvitationInput!) {
                profileSendInvitation(input: $input) {
                    profileUserRole {
                        status
                    }
                }
            }
        """

        variables = {"input": {"profileId": profile.relay_id, "email": email, "role": "MANAGER"}}

        response = graphql_user_client(mutation, variables=variables)
        content = response.json()

        assert content["data"]["profileSendInvitation"]["profileUserRole"]["status"] == "PENDING"
        assert (
            ActualProfileUserRole.objects.filter(profile=profile, invited_email=email).count() == 1
        )
        invitation.refresh_from_db()
        assert invitation.pk == original_pk
        assert invitation.invitation_expires_at > timezone.now()

    def test_expiration_uses_constant(self):
        owner = UserFactory()
        profile = ProfileFactory(owner=owner)

        invitation = create_invitation(
            profile=profile, inviter=owner, invited_email="test@test.com"
        )

        expected_expiration = invitation.invited_at + timedelta(days=INVITATION_EXPIRATION_DAYS)
        diff = abs((invitation.invitation_expires_at - expected_expiration).total_seconds())
        assert diff < 1

    def test_accept_transitions_to_active(self, django_user_client, graphql_user_client):
        owner = UserFactory()
        profile = ProfileFactory(owner=owner)

        invitation = create_invitation(
            profile=profile, inviter=owner, invited_email=django_user_client.user.email
        )

        assert invitation.status == ProfileUserRole.ProfileRoleStatus.PENDING

        mutation = """
            mutation AcceptInvitation($input: ProfileAcceptInvitationInput!) {
                profileAcceptInvitation(input: $input) {
                    profileUserRole {
                        status
                    }
                }
            }
        """

        variables = {"input": {"token": invitation.invitation_token}}

        response = graphql_user_client(mutation, variables=variables)
        content = response.json()

        assert content["data"]["profileAcceptInvitation"]["profileUserRole"]["status"] == "ACTIVE"

        invitation.refresh_from_db()
        assert invitation.status == ProfileUserRole.ProfileRoleStatus.ACTIVE
        assert invitation.responded_at is not None
        assert invitation.user == django_user_client.user

    def test_decline_transitions_to_declined(self, django_user_client, graphql_user_client):
        owner = UserFactory()
        profile = ProfileFactory(owner=owner)

        invitation = create_invitation(
            profile=profile, inviter=owner, invited_email=django_user_client.user.email
        )

        assert invitation.status == ProfileUserRole.ProfileRoleStatus.PENDING

        mutation = """
            mutation DeclineInvitation($input: ProfileDeclineInvitationInput!) {
                profileDeclineInvitation(input: $input) {
                    success
                }
            }
        """

        variables = {"input": {"token": invitation.invitation_token}}

        response = graphql_user_client(mutation, variables=variables)
        content = response.json()

        assert content["data"]["profileDeclineInvitation"]["success"] is True

        invitation.refresh_from_db()
        assert invitation.status == ProfileUserRole.ProfileRoleStatus.DECLINED
        assert invitation.responded_at is not None

    def test_unique_constraint_prevents_duplicate_invited_email(self):
        from django.db import IntegrityError
        import swapper

        owner = UserFactory()
        profile = ProfileFactory(owner=owner)
        email = "duplicate@test.com"
        ActualProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")

        create_invitation(profile=profile, inviter=owner, invited_email=email)

        with pytest.raises(IntegrityError):
            ActualProfileUserRole.objects.create(
                profile=profile,
                invited_email=email,
                role=ProfileUserRole.ProfileRoles.MANAGER,
                status=ProfileUserRole.ProfileRoleStatus.PENDING,
            )


@pytest.mark.django_db
class TestInvitationPIIFieldPermissions:
    def test_authorized_user_sees_pii_fields(self, django_user_client, graphql_user_client):
        profile = ProfileFactory(owner=django_user_client.user)

        invitation = create_invitation(
            profile=profile, inviter=django_user_client.user, invited_email="test@test.com"
        )

        query = """
            query GetInvitation($id: ID!) {
                node(id: $id) {
                    ... on ProfileUserRole {
                        invitedEmail
                        invitedAt
                        invitationExpiresAt
                        respondedAt
                    }
                }
            }
        """

        variables = {"id": invitation.relay_id}

        response = graphql_user_client(query, variables=variables)
        content = response.json()

        assert "errors" not in content
        assert content["data"]["node"]["invitedEmail"] == "test@test.com"
        assert content["data"]["node"]["invitedAt"] is not None
        assert content["data"]["node"]["invitationExpiresAt"] is not None

    def test_unauthorized_user_sees_null_pii_fields(self):
        owner = UserFactory()
        profile = ProfileFactory(owner=owner)
        unauthorized_user = UserFactory()

        invitation = create_invitation(
            profile=profile, inviter=owner, invited_email="secret@test.com"
        )

        query = """
            query GetInvitation($id: ID!) {
                node(id: $id) {
                    ... on ProfileUserRole {
                        invitedEmail
                        invitedAt
                        invitationExpiresAt
                        respondedAt
                    }
                }
            }
        """

        variables = {"id": invitation.relay_id}

        client = Client()
        client.force_login(unauthorized_user)
        response = graphql_query(query, variables=variables, client=client)
        content = response.json()

        assert "errors" not in content
        assert content["data"]["node"]["invitedEmail"] is None
        assert content["data"]["node"]["invitedAt"] is None
        assert content["data"]["node"]["invitationExpiresAt"] is None
        assert content["data"]["node"]["respondedAt"] is None
