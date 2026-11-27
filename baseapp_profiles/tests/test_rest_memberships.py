import pytest
import swapper
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient

from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.services import invitations as service

from .factories import ProfileFactory, ProfileUserRoleFactory

pytestmark = pytest.mark.django_db

User = get_user_model()
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
ADMIN = ProfileUserRole.ProfileRoles.ADMIN
MANAGER = ProfileUserRole.ProfileRoles.MANAGER
Status = ProfileUserRole.ProfileRoleStatus

MEMBERS = "/v1/profile-members"
INVITATIONS = "/v1/profile-invitations"
PASSWORD = "c0rrect-Horse-battery"  # NOSONAR


@pytest.fixture(autouse=True)
def clear_throttle_cache() -> None:
    cache.clear()


@pytest.fixture
def org() -> tuple:
    """An ownerless profile with an admin and a manager."""
    profile = ProfileFactory(owner=None, name="Acme")
    admin = ProfileUserRoleFactory(profile=profile, role=ADMIN)
    manager = ProfileUserRoleFactory(profile=profile, role=MANAGER)
    return profile, admin, manager


def client_for(user=None, profile=None) -> APIClient:
    client = APIClient()
    if user is not None:
        client.force_authenticate(user)
    if profile is not None:
        client.credentials(HTTP_CURRENT_PROFILE=profile.relay_id)
    return client


class TestMembers:
    def test_members_list_the_profile_members(self, org) -> None:
        profile, admin, manager = org
        ProfileUserRoleFactory(profile=profile, status=Status.PENDING, role=MANAGER)  # an invite
        ProfileUserRoleFactory(role=ADMIN)  # another profile

        for viewer in (admin, manager):
            response = client_for(viewer.user, profile).get(MEMBERS)
            assert response.status_code == 200
            ids = {row["id"] for row in response.json()["results"]}
            assert ids == {admin.pk, manager.pk}

        row = next(r for r in response.json()["results"] if r["id"] == admin.pk)
        assert row["role"] == ADMIN
        assert row["status"] == Status.ACTIVE
        assert row["user"]["email"] == admin.user.email
        assert row["user"]["profile"]["id"] == admin.user.profile.relay_id

    def test_filters(self, org) -> None:
        profile, admin, manager = org

        response = client_for(admin.user, profile).get(MEMBERS, {"role": MANAGER})

        assert [r["id"] for r in response.json()["results"]] == [manager.pk]

    def test_outsiders_are_refused(self, org) -> None:
        profile, _, _ = org

        assert client_for(UserFactory(), profile).get(MEMBERS).status_code == 403
        assert client_for(None, profile).get(MEMBERS).status_code == 401

    def test_without_the_header_the_users_own_profile_is_used(self) -> None:
        user = UserFactory()

        response = client_for(user).get(MEMBERS)

        assert response.status_code == 200
        assert response.json()["results"] == []

    def test_an_admin_changes_a_role(self, org) -> None:
        profile, admin, manager = org

        response = client_for(admin.user, profile).patch(
            f"{MEMBERS}/{manager.pk}", {"role": ADMIN}, format="json"
        )

        assert response.status_code == 200
        assert response.json()["role"] == ADMIN
        manager.refresh_from_db()
        assert manager.role == ADMIN

    def test_an_invalid_role_is_refused(self, org) -> None:
        profile, admin, manager = org

        response = client_for(admin.user, profile).patch(
            f"{MEMBERS}/{manager.pk}", {"role": 99}, format="json"
        )

        assert response.status_code == 400
        assert "role" in response.json()

    def test_a_manager_cannot_manage(self, org) -> None:
        profile, admin, manager = org
        client = client_for(manager.user, profile)

        assert client.patch(f"{MEMBERS}/{admin.pk}", {"role": MANAGER}).status_code == 403
        assert client.post(f"{MEMBERS}/{admin.pk}/deactivate").status_code == 403
        assert client.delete(f"{MEMBERS}/{admin.pk}").status_code == 403

    def test_deactivate_and_reactivate(self, org) -> None:
        profile, admin, manager = org
        client = client_for(admin.user, profile)

        response = client.post(f"{MEMBERS}/{manager.pk}/deactivate")
        assert response.status_code == 200
        assert response.json()["status"] == Status.INACTIVE
        assert response.json()["deactivated_by"] == admin.user.pk

        response = client.post(f"{MEMBERS}/{manager.pk}/reactivate")
        assert response.status_code == 200
        assert response.json()["status"] == Status.ACTIVE

    def test_the_last_admin_is_kept(self, org) -> None:
        profile, admin, _ = org
        client = client_for(admin.user, profile)

        response = client.post(f"{MEMBERS}/{admin.pk}/deactivate")

        assert response.status_code == 400
        assert response.json() == {
            "non_field_errors": ["A profile must keep at least one active admin"],
            "code": "last_admin",
        }
        assert client.delete(f"{MEMBERS}/{admin.pk}").json()["code"] == "last_admin"

    def test_remove(self, org) -> None:
        profile, admin, manager = org

        response = client_for(admin.user, profile).delete(f"{MEMBERS}/{manager.pk}")

        assert response.status_code == 204
        assert not ProfileUserRole.objects.filter(pk=manager.pk).exists()

    def test_members_of_another_profile_are_out_of_reach(self, org) -> None:
        profile, admin, _ = org
        elsewhere = ProfileUserRoleFactory()

        response = client_for(admin.user, profile).delete(f"{MEMBERS}/{elsewhere.pk}")

        assert response.status_code == 404


class TestInvitations:
    def test_an_admin_invites_in_bulk(self, org, mailoutbox) -> None:
        profile, admin, _ = org

        response = client_for(admin.user, profile).post(
            INVITATIONS,
            {
                "emails": ["one@example.com"],
                "invitations": [{"email": "two@example.com", "first_name": "Two"}],
                "role": ADMIN,
                "message": "Welcome",
            },
            format="json",
        )

        assert response.status_code == 201, response.json()
        data = response.json()
        assert data["emails_sent"] == 2
        assert data["emails_held"] == 0
        assert [i["invited_email"] for i in data["invitations"]] == [
            "one@example.com",
            "two@example.com",
        ]
        second = data["invitations"][1]
        assert second["invited_first_name"] == "Two"
        assert second["message"] == "Welcome"
        assert second["invited_by"] == admin.user.pk
        assert second["role"] == ADMIN
        assert "invitation_token" not in second
        assert len(mailoutbox) == 2

    def test_a_manager_cannot_invite(self, org) -> None:
        profile, _, manager = org

        response = client_for(manager.user, profile).post(
            INVITATIONS, {"emails": ["a@example.com"]}, format="json"
        )

        assert response.status_code == 403

    def test_input_is_validated(self, org) -> None:
        profile, admin, _ = org
        client = client_for(admin.user, profile)

        response = client.post(INVITATIONS, {}, format="json")
        assert response.status_code == 400
        assert response.json() == {"non_field_errors": ["At least one email is required"]}

        response = client.post(INVITATIONS, {"emails": ["not-an-email"]}, format="json")
        assert response.status_code == 400
        assert "emails" in response.json()

    def test_a_duplicate_is_reported_with_its_code(self, org) -> None:
        profile, admin, _ = org
        client = client_for(admin.user, profile)
        client.post(INVITATIONS, {"emails": ["a@example.com"]}, format="json")

        response = client.post(INVITATIONS, {"emails": ["a@example.com"]}, format="json")

        assert response.status_code == 400
        assert response.json()["code"] == "duplicate_invitation"

    def test_list_filter_resend_and_cancel(self, org, settings) -> None:
        settings.BASEAPP_PROFILES_INVITATION_KEEP_HISTORY = True
        profile, admin, manager = org
        invitation = service.send_invitations(profile, ["a@example.com"]).invitations[0]
        service.send_invitations(ProfileFactory(), ["elsewhere@example.com"])

        response = client_for(manager.user, profile).get(INVITATIONS, {"status": Status.PENDING})
        assert [i["id"] for i in response.json()["results"]] == [invitation.pk]

        client = client_for(admin.user, profile)
        response = client.post(f"{INVITATIONS}/{invitation.pk}/resend")
        assert response.status_code == 200
        assert response.json()["emails_sent"] == 1
        assert response.json()["invitations"][0]["sent_count"] == 2

        response = client.post(f"{INVITATIONS}/{invitation.pk}/cancel")
        assert response.status_code == 200
        assert response.json()["status"] == Status.CANCELLED

        response = client.post(f"{INVITATIONS}/{invitation.pk}/cancel")
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_status"

    def test_cancel_without_history_deletes(self, org) -> None:
        profile, admin, _ = org
        invitation = service.send_invitations(profile, ["a@example.com"]).invitations[0]

        response = client_for(admin.user, profile).post(f"{INVITATIONS}/{invitation.pk}/cancel")

        assert response.status_code == 204
        assert not ProfileUserRole.objects.filter(pk=invitation.pk).exists()


class TestTokenEndpoints:
    @pytest.fixture
    def invitation(self, org) -> "ProfileUserRole":
        profile, _, _ = org
        return service.send_invitations(profile, ["ann@example.com"], role=ADMIN).invitations[0]

    def _url(self, invitation, suffix="") -> str:
        return f"{INVITATIONS}/by-token/{invitation.invitation_token}{suffix}"

    def test_lookup_is_public_and_minimal(self, org) -> None:
        profile, admin, _ = org
        invitation = service.send_invitations(
            profile,
            [{"email": "ann@example.com", "first_name": "Ann", "last_name": "Lee"}],
            role=ADMIN,
            invited_by=admin.user,
            message="Welcome aboard",
        ).invitations[0]

        response = client_for().get(self._url(invitation))

        assert response.status_code == 200
        # The same summary the GraphQL `profileInvitationPreview` gives, and nothing else.
        assert response.json() == {
            "profile_name": "Acme",
            "profile_image": None,
            "invited_email": "ann@example.com",
            "invited_first_name": "Ann",
            "invited_last_name": "Lee",
            "inviter_name": admin.user.get_full_name() or admin.user.email,
            "message": "Welcome aboard",
            "role": ADMIN,
            "status": Status.PENDING,
            "expires_at": response.json()["expires_at"],
            "requires_sign_in": False,
        }
        assert response.json()["expires_at"] is not None

    def test_lookup_tells_an_invitee_with_an_account_to_sign_in(self, invitation) -> None:
        UserFactory(email="ann@example.com")

        response = client_for().get(self._url(invitation))

        assert response.json()["requires_sign_in"] is True

    def test_lookup_of_an_unknown_token(self) -> None:
        response = client_for().get(f"{INVITATIONS}/by-token/unknown")

        assert response.status_code == 404
        assert response.json()["code"] == "invalid_token"

    def test_signup_is_disabled_by_default(self, invitation) -> None:
        response = client_for().post(
            self._url(invitation, "/accept-with-signup"), {"password": PASSWORD}
        )

        assert response.status_code == 403
        assert response.json()["code"] == "signup_disabled"

    def test_signup_accepts_anonymously(self, invitation, settings) -> None:
        settings.BASEAPP_PROFILES_INVITATION_SIGNUP_ENABLED = True

        response = client_for().post(
            self._url(invitation, "/accept-with-signup"),
            {"password": PASSWORD, "first_name": "Ann", "last_name": "Lee"},
            format="json",
        )

        assert response.status_code == 201, response.json()
        assert response.json()["email"] == "ann@example.com"
        assert response.json()["status"] == Status.ACTIVE
        assert response.json()["profile"]["name"] == "Acme"
        assert User.objects.get(email="ann@example.com").check_password(PASSWORD)

    def test_signup_with_an_existing_account_conflicts(self, invitation, settings) -> None:
        settings.BASEAPP_PROFILES_INVITATION_SIGNUP_ENABLED = True
        UserFactory(email="ann@example.com")

        response = client_for().post(
            self._url(invitation, "/accept-with-signup"), {"password": PASSWORD}
        )

        assert response.status_code == 409
        assert response.json()["code"] == "user_exists"

    def test_signup_does_not_bring_back_a_deactivated_superuser(self, invitation, settings) -> None:
        settings.BASEAPP_PROFILES_INVITATION_SIGNUP_ENABLED = True
        UserFactory(email="ann@example.com", is_active=False, is_superuser=True)

        response = client_for().post(
            self._url(invitation, "/accept-with-signup"), {"password": PASSWORD}
        )

        assert response.status_code == 403
        assert response.json()["code"] == "account_inactive"
        assert not User.objects.get(email="ann@example.com").is_active

    def test_signup_needs_a_password(self, invitation, settings) -> None:
        settings.BASEAPP_PROFILES_INVITATION_SIGNUP_ENABLED = True

        response = client_for().post(self._url(invitation, "/accept-with-signup"), {})

        assert response.status_code == 400
        assert "password" in response.json()

    def test_a_signed_in_invitee_accepts(self, invitation) -> None:
        user = UserFactory(email="ann@example.com")

        response = client_for(user).post(self._url(invitation, "/accept"))

        assert response.status_code == 200
        assert response.json()["status"] == Status.ACTIVE
        invitation.refresh_from_db()
        assert invitation.user == user

    def test_a_signed_in_invitee_declines(self, invitation) -> None:
        user = UserFactory(email="ann@example.com")

        response = client_for(user).post(self._url(invitation, "/decline"))

        assert response.status_code == 200
        assert response.json()["status"] == Status.DECLINED

    def test_someone_else_cannot_accept(self, invitation) -> None:
        response = client_for(UserFactory()).post(self._url(invitation, "/accept"))

        assert response.status_code == 403
        assert response.json()["code"] == "wrong_user"

    def test_accept_needs_a_sign_in(self, invitation) -> None:
        assert client_for().post(self._url(invitation, "/accept")).status_code == 401

    def test_public_endpoints_are_rate_limited(self, invitation, settings) -> None:
        settings.BASEAPP_PROFILES_INVITATION_PUBLIC_RATE = "2/hour"
        client = client_for()

        statuses = [client.get(self._url(invitation)).status_code for _ in range(3)]

        assert statuses == [200, 200, 429]


class TestErrors:
    def test_an_unexpected_error_is_not_described_to_the_client(self, org, monkeypatch) -> None:
        profile, admin, manager = org

        def explode(*args, **kwargs) -> None:
            raise RuntimeError("secret detail: db-host-17")

        monkeypatch.setattr(
            "baseapp_profiles.rest_framework.memberships.views.member_service.deactivate_member",
            explode,
        )
        client = client_for(admin.user, profile)
        client.raise_request_exception = False

        response = client.post(f"{MEMBERS}/{manager.pk}/deactivate")

        assert response.status_code == 500
        assert b"secret detail" not in response.content

    def test_a_refusal_carries_only_its_message_and_code(self, org) -> None:
        profile, admin, _ = org

        response = client_for(admin.user, profile).post(f"{MEMBERS}/{admin.pk}/deactivate")

        assert response.status_code == 400
        assert response.json() == {
            "non_field_errors": ["A profile must keep at least one active admin"],
            "code": "last_admin",
        }


class TestMemberListQueries:
    def _url_path_queries(self, client) -> int:
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as queries:
            assert client.get(MEMBERS).status_code == 200
        return len([query for query in queries if "urlpath" in query["sql"]])

    def test_the_member_list_loads_url_paths_in_one_query(self, org) -> None:
        profile, admin, _ = org
        client = client_for(admin.user, profile)
        for _index in range(4):
            ProfileUserRoleFactory(profile=profile, role=MANAGER)

        response = client.get(MEMBERS)

        assert self._url_path_queries(client) == 1
        assert all(row["user"]["profile"]["url_path"] for row in response.json()["results"])


class TestSentCount:
    def test_a_publish_refused_on_commit_is_taken_off_the_count(
        self, org, settings, django_capture_on_commit_callbacks
    ) -> None:
        from unittest.mock import patch

        from baseapp_profiles import tasks

        profile, _, _ = org
        settings.BASEAPP_PROFILES_INVITATION_ASYNC_SEND = True
        settings.CELERY_TASK_ALWAYS_EAGER = False

        with patch.object(
            tasks.send_invitation_email_task, "delay", side_effect=[OSError("down"), None]
        ):
            with django_capture_on_commit_callbacks(execute=True):
                result = service.send_invitations(profile, ["ann@example.com", "bob@example.com"])
                assert result.emails_sent == 2

        assert result.emails_sent == 1
