from unittest.mock import patch

import pytest
import swapper
from django.contrib.auth.models import Permission
from django.db import IntegrityError

from baseapp_core.tests.factories import UserFactory

from .factories import ProfileFactory, ProfileUserRoleFactory

pytestmark = pytest.mark.django_db

ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")


PROFILE_USER_ROLE_CREATE_GRAPHQL = """
mutation ProfileUserRoleCreateMutation($input: ProfileUserRoleCreateInput!) {
    profileUserRoleCreate(input: $input) {
        profileUserRoles {
            id
            role
            status
        }
    }
}
"""


def _add_member_permission(user):
    perm = Permission.objects.get(
        content_type__app_label=ProfileUserRole._meta.app_label, codename="add_profileuserrole"
    )
    user.user_permissions.add(perm)


def test_user_with_permission_can_add_member(django_user_client, graphql_user_client):
    user = django_user_client.user
    _add_member_permission(user)
    profile = ProfileFactory(owner=user)
    new_member = UserFactory()

    response = graphql_user_client(
        PROFILE_USER_ROLE_CREATE_GRAPHQL,
        variables={
            "input": {
                "profileId": profile.relay_id,
                "usersIds": [new_member.relay_id],
                "roleType": "MANAGER",
            }
        },
    )
    content = response.json()

    assert "errors" not in content, content.get("errors")
    roles = content["data"]["profileUserRoleCreate"]["profileUserRoles"]
    assert len(roles) == 1
    assert ProfileUserRole.objects.filter(profile=profile, user=new_member).exists()


def test_adding_an_existing_member_returns_a_friendly_error(
    django_user_client, graphql_user_client
):
    user = django_user_client.user
    _add_member_permission(user)
    profile = ProfileFactory(owner=user)
    existing_member = UserFactory()
    ProfileUserRoleFactory(
        profile=profile, user=existing_member, role=ProfileUserRole.ProfileRoles.MANAGER
    )

    response = graphql_user_client(
        PROFILE_USER_ROLE_CREATE_GRAPHQL,
        variables={
            "input": {
                "profileId": profile.relay_id,
                "usersIds": [existing_member.relay_id],
                "roleType": "MANAGER",
            }
        },
    )
    content = response.json()

    assert content["errors"][0]["extensions"]["code"] == "already_member"
    # The raw unique-constraint / DB error must never reach the client.
    assert "duplicate key" not in content["errors"][0]["message"]
    # No duplicate row was created.
    assert ProfileUserRole.objects.filter(profile=profile, user=existing_member).count() == 1


def test_duplicate_user_ids_in_one_request_create_a_single_membership(
    django_user_client, graphql_user_client
):
    user = django_user_client.user
    _add_member_permission(user)
    profile = ProfileFactory(owner=user)
    new_member = UserFactory()

    response = graphql_user_client(
        PROFILE_USER_ROLE_CREATE_GRAPHQL,
        variables={
            "input": {
                "profileId": profile.relay_id,
                "usersIds": [new_member.relay_id, new_member.relay_id],
                "roleType": "MANAGER",
            }
        },
    )
    content = response.json()

    assert "errors" not in content, content.get("errors")
    roles = content["data"]["profileUserRoleCreate"]["profileUserRoles"]
    assert len(roles) == 1
    assert ProfileUserRole.objects.filter(profile=profile, user=new_member).count() == 1


def test_integrity_error_that_is_not_a_duplicate_returns_a_generic_error(
    django_user_client, graphql_user_client
):
    user = django_user_client.user
    _add_member_permission(user)
    profile = ProfileFactory(owner=user)
    new_member = UserFactory()

    # An IntegrityError that is not an existing membership (e.g. a FK violation) must return a
    # generic error, not be misreported as "already_member".
    with patch.object(ProfileUserRole.objects, "bulk_create", side_effect=IntegrityError("boom")):
        response = graphql_user_client(
            PROFILE_USER_ROLE_CREATE_GRAPHQL,
            variables={
                "input": {
                    "profileId": profile.relay_id,
                    "usersIds": [new_member.relay_id],
                    "roleType": "MANAGER",
                }
            },
        )
    content = response.json()

    assert content["errors"][0]["extensions"]["code"] == "add_member_failed"
    assert not ProfileUserRole.objects.filter(profile=profile, user=new_member).exists()


def test_cannot_add_the_owner_as_a_member(django_user_client, graphql_user_client):
    user = django_user_client.user
    _add_member_permission(user)
    profile = ProfileFactory(owner=user)

    response = graphql_user_client(
        PROFILE_USER_ROLE_CREATE_GRAPHQL,
        variables={
            "input": {
                "profileId": profile.relay_id,
                "usersIds": [user.relay_id],
                "roleType": "MANAGER",
            }
        },
    )
    content = response.json()

    assert content["errors"][0]["extensions"]["code"] == "cannot_add_owner"
    assert not ProfileUserRole.objects.filter(profile=profile, user=user).exists()
