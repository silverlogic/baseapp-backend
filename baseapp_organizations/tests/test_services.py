import pytest
import swapper
from django.contrib.admin.sites import AdminSite
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory

from baseapp_core.tests.factories import UserFactory
from baseapp_organizations.admin import OrganizationAdmin
from baseapp_organizations.services import (
    OrganizationAccountService,
    OrganizationService,
    ensure_profiles_for_organizations,
)
from baseapp_profiles.tests.factories import ProfileUserRoleFactory

from .factories import OrganizationFactory

pytestmark = pytest.mark.django_db

Organization = swapper.load_model("baseapp_organizations", "Organization")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
ADMIN = ProfileUserRole.ProfileRoles.ADMIN
MANAGER = ProfileUserRole.ProfileRoles.MANAGER


class TestOrganizationService:
    def test_creates_an_organization_with_an_ownerless_profile(self) -> None:
        organization = OrganizationService.create("Acme Corporation")

        profile = organization.profile
        assert profile is not None
        assert profile.owner_id is None
        assert profile.name == "Acme Corporation"
        assert profile.target == organization
        assert profile.target_content_type == ContentType.objects.get_for_model(Organization)
        assert profile.url_path.path == "/acmecorporation"

    def test_takes_an_owner_and_a_handle(self) -> None:
        owner = UserFactory()

        organization = OrganizationService.create("Acme", owner=owner, url_path="acme-holdings")

        assert organization.profile.owner == owner
        assert [p.path for p in organization.profile.url_paths.all()] == ["/acmeholdings"]

    def test_the_profile_name_follows_the_organization(self) -> None:
        organization = OrganizationService.create("Acme")

        organization.name = "Acme Two"
        organization.save()

        organization.profile.refresh_from_db()
        assert organization.profile.name == "Acme Two"

    def test_ensure_profile_is_idempotent(self) -> None:
        organization = OrganizationService.create("Acme")
        profile = organization.profile

        assert OrganizationService.ensure_profile(organization) == profile

    def test_backfills_organizations_without_a_profile(self) -> None:
        bare = [OrganizationFactory(name="One"), OrganizationFactory(name="Two")]
        OrganizationService.create("Has one")

        assert ensure_profiles_for_organizations() == 2
        assert ensure_profiles_for_organizations() == 0

        for organization in bare:
            organization.refresh_from_db()
            assert organization.profile.name == organization.name
            assert organization.profile.owner_id is None


class TestAdmin:
    def _save(self, organization, user, change) -> None:
        request = RequestFactory().post("/")
        request.user = user
        OrganizationAdmin(Organization, AdminSite()).save_model(request, organization, None, change)

    def test_the_creating_admin_owns_the_profile(self) -> None:
        staff = UserFactory(is_staff=True)

        organization = Organization(name="Acme")
        self._save(organization, staff, change=False)

        assert organization.profile.owner == staff

    def test_editing_an_ownerless_organization_keeps_its_profile(self) -> None:
        organization = OrganizationService.create("Acme")
        profile_pk = organization.profile_id

        organization.name = "Acme Renamed"
        self._save(organization, UserFactory(is_staff=True), change=True)

        organization.refresh_from_db()
        assert organization.profile_id == profile_pk
        assert organization.profile.owner_id is None


class TestAccountDeletionVeto:
    service = OrganizationAccountService()

    def test_the_only_admin_of_an_ownerless_organization_is_held_back(self) -> None:
        organization = OrganizationService.create("Acme")
        admin = ProfileUserRoleFactory(profile=organization.profile, role=ADMIN)

        assert "only admin" in str(self.service.get_account_deletion_block_reason(admin.user))

    def test_another_admin_lets_them_go(self) -> None:
        organization = OrganizationService.create("Acme")
        admin = ProfileUserRoleFactory(profile=organization.profile, role=ADMIN)
        ProfileUserRoleFactory(profile=organization.profile, role=ADMIN)

        assert self.service.get_account_deletion_block_reason(admin.user) is None

    def test_managers_are_not_held_back(self) -> None:
        organization = OrganizationService.create("Acme")
        ProfileUserRoleFactory(profile=organization.profile, role=ADMIN)
        manager = ProfileUserRoleFactory(profile=organization.profile, role=MANAGER)

        assert self.service.get_account_deletion_block_reason(manager.user) is None

    def test_an_organization_with_an_owner_only_holds_back_the_owner(self) -> None:
        owner = UserFactory()
        organization = OrganizationService.create("Acme", owner=owner)
        admin = ProfileUserRoleFactory(profile=organization.profile, role=ADMIN)

        assert self.service.get_account_deletion_block_reason(admin.user) is None
        assert "owner" in str(self.service.get_account_deletion_block_reason(owner))
