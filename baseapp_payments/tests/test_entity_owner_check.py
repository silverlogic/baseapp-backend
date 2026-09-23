"""Who may bill an entity, and what happens for entity models the block does not know.

`STRIPE_CUSTOMER_ENTITY_MODEL` is runtime-configurable, so `baseapp_payments` cannot
know what ownership means for every model a project might point it at. It used to guess
by comparing the entity's pk to the user's, which makes organization 5 look owned by
user 5.
"""

from unittest.mock import patch

import pytest
import swapper
from django.contrib.auth.models import AnonymousUser
from django.test import override_settings

from baseapp_core.tests.factories import UserFactory
from baseapp_organizations.tests.factories import OrganizationFactory
from baseapp_payments.permissions import is_entity_owner
from baseapp_profiles.tests.factories import ProfileFactory, ProfileUserRoleFactory

ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")

pytestmark = pytest.mark.django_db


def allow_everything(entity, user_obj) -> bool:
    return True


class TestProfileEntities:
    def test_owner_may_bill_their_profile(self):
        user = UserFactory()
        assert is_entity_owner(ProfileFactory(owner=user), user) is True

    def test_active_admin_member_may_bill(self):
        membership = ProfileUserRoleFactory(role=ProfileUserRole.ProfileRoles.ADMIN)
        assert is_entity_owner(membership.profile, membership.user) is True

    def test_member_without_the_admin_role_may_not(self):
        membership = ProfileUserRoleFactory(role=ProfileUserRole.ProfileRoles.MANAGER)
        assert is_entity_owner(membership.profile, membership.user) is False

    def test_deactivated_admin_may_not(self):
        membership = ProfileUserRoleFactory(
            role=ProfileUserRole.ProfileRoles.ADMIN,
            status=ProfileUserRole.ProfileRoleStatus.INACTIVE,
        )
        assert is_entity_owner(membership.profile, membership.user) is False

    def test_unrelated_user_may_not(self):
        assert is_entity_owner(ProfileFactory(), UserFactory()) is False

    def test_anonymous_user_owns_nothing(self):
        assert is_entity_owner(ProfileFactory(), AnonymousUser()) is False

    @patch("baseapp_payments.permissions.apps.is_installed", return_value=False)
    def test_profiles_being_absent_denies_rather_than_crashes(self, _mock_is_installed):
        # `baseapp_profiles` is optional, so the Profile branch has to be skippable —
        # and skipping it must not fall through to some looser comparison.
        user = UserFactory()
        assert is_entity_owner(ProfileFactory(owner=user), user) is False


class TestUserEntities:
    def test_a_user_entity_is_matched_by_pk(self):
        user = UserFactory()
        assert is_entity_owner(user, user) is True

    def test_another_user_is_not(self):
        assert is_entity_owner(UserFactory(), UserFactory()) is False


class TestEntityModelsTheBlockCannotVouchFor:
    def test_an_entity_sharing_a_pk_with_the_user_is_denied(self):
        # The regression this check exists for: the old fallback compared these two pks
        # and called it ownership.
        user = UserFactory()
        organization = OrganizationFactory.build(id=user.pk)
        assert is_entity_owner(organization, user) is False

    @override_settings(
        BASEAPP_PAYMENTS_ENTITY_OWNER_CHECK=(
            "baseapp_payments.tests.test_entity_owner_check.allow_everything"
        )
    )
    def test_a_project_supplied_check_replaces_the_default(self):
        user = UserFactory()
        organization = OrganizationFactory.build(id=user.pk)
        assert is_entity_owner(organization, user) is True

    @override_settings(
        BASEAPP_PAYMENTS_ENTITY_OWNER_CHECK=(
            "baseapp_payments.tests.test_entity_owner_check.allow_everything"
        )
    )
    def test_a_project_supplied_check_still_cannot_authorize_anonymous(self):
        assert is_entity_owner(OrganizationFactory.build(), AnonymousUser()) is False
