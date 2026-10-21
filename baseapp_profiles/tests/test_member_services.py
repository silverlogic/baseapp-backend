import pytest
import swapper
from django.core.exceptions import ValidationError
from django.db import models
from django.test.utils import isolate_apps

from baseapp_core.tests.factories import UserFactory
from baseapp_profiles import signals
from baseapp_profiles.exceptions import ProfileMembershipError
from baseapp_profiles.graphql.object_types import ProfileRoleTypesEnum
from baseapp_profiles.models import AbstractProfileUserRole
from baseapp_profiles.rest_framework.memberships.serializers import (
    ProfileInvitationSendSerializer,
    ProfileMemberRoleSerializer,
)
from baseapp_profiles.services.members import (
    change_member_role,
    deactivate_member,
    reactivate_member,
    remove_member,
    validate_role,
)

from .factories import ProfileFactory, ProfileUserRoleFactory

pytestmark = pytest.mark.django_db

ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
ADMIN = ProfileUserRole.ProfileRoles.ADMIN
MANAGER = ProfileUserRole.ProfileRoles.MANAGER
Status = ProfileUserRole.ProfileRoleStatus


class TestLastAdminGuard:
    """An ownerless profile is run by its admins, so it must never lose the last one."""

    def test_ownerless_profile_keeps_its_last_admin(self) -> None:
        profile = ProfileFactory(owner=None)
        admin = ProfileUserRoleFactory(profile=profile, role=ADMIN)

        for action in (
            lambda: deactivate_member(admin),
            lambda: remove_member(admin),
            lambda: change_member_role(admin, MANAGER),
        ):
            with pytest.raises(ProfileMembershipError) as excinfo:
                action()
            assert excinfo.value.code == "last_admin"

        admin.refresh_from_db()
        assert (admin.role, admin.status) == (ADMIN, Status.ACTIVE)

    def test_another_active_admin_lets_one_go(self) -> None:
        profile = ProfileFactory(owner=None)
        first = ProfileUserRoleFactory(profile=profile, role=ADMIN)
        ProfileUserRoleFactory(profile=profile, role=ADMIN)

        deactivate_member(first)

        first.refresh_from_db()
        assert first.status == Status.INACTIVE

    def test_a_deactivated_admin_does_not_count(self) -> None:
        profile = ProfileFactory(owner=None)
        admin = ProfileUserRoleFactory(profile=profile, role=ADMIN)
        ProfileUserRoleFactory(profile=profile, role=ADMIN, status=Status.INACTIVE)

        with pytest.raises(ProfileMembershipError):
            remove_member(admin)

    def test_managers_are_not_guarded(self) -> None:
        profile = ProfileFactory(owner=None)
        ProfileUserRoleFactory(profile=profile, role=ADMIN)
        manager = ProfileUserRoleFactory(profile=profile, role=MANAGER)

        remove_member(manager)

        assert not ProfileUserRole.objects.filter(pk=manager.pk).exists()

    def test_a_profile_with_an_owner_is_not_guarded_by_default(self) -> None:
        profile = ProfileFactory()
        admin = ProfileUserRoleFactory(profile=profile, role=ADMIN)

        remove_member(admin)

        assert not ProfileUserRole.objects.filter(pk=admin.pk).exists()

    def test_the_setting_guards_profiles_with_an_owner_too(self, settings) -> None:
        settings.BASEAPP_PROFILES_PROTECT_LAST_ADMIN = True
        admin = ProfileUserRoleFactory(profile=ProfileFactory(), role=ADMIN)

        with pytest.raises(ProfileMembershipError) as excinfo:
            change_member_role(admin, MANAGER)
        assert excinfo.value.code == "last_admin"

    def test_promoting_is_never_blocked(self) -> None:
        profile = ProfileFactory(owner=None)
        ProfileUserRoleFactory(profile=profile, role=ADMIN)
        manager = ProfileUserRoleFactory(profile=profile, role=MANAGER)

        change_member_role(manager, ADMIN)

        manager.refresh_from_db()
        assert manager.role == ADMIN


class TestMembershipLifecycle:
    def test_deactivate_records_who_and_when(
        self, signal_recorder, django_capture_on_commit_callbacks
    ) -> None:
        calls = signal_recorder(signals.member_deactivated)
        admin_user = UserFactory()
        member = ProfileUserRoleFactory(role=MANAGER)

        with django_capture_on_commit_callbacks(execute=True):
            deactivate_member(member, by=admin_user)

        member.refresh_from_db()
        assert member.status == Status.INACTIVE
        assert member.deactivated_at is not None
        assert member.deactivated_by == admin_user
        assert len(calls) == 1
        assert calls[0]["sender"] is ProfileUserRole
        assert calls[0]["instance"].pk == member.pk
        assert calls[0]["by"] == admin_user

    def test_signals_wait_for_the_transaction_to_commit(
        self, signal_recorder, django_capture_on_commit_callbacks
    ) -> None:
        calls = signal_recorder(signals.member_deactivated)
        member = ProfileUserRoleFactory()

        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            deactivate_member(member)

        assert calls == []
        assert len(callbacks) == 1

    def test_only_active_members_can_be_deactivated(self) -> None:
        member = ProfileUserRoleFactory(status=Status.PENDING)

        with pytest.raises(ProfileMembershipError) as excinfo:
            deactivate_member(member)
        assert excinfo.value.code == "invalid_status"

    def test_reactivate_clears_the_audit_fields(
        self, signal_recorder, django_capture_on_commit_callbacks
    ) -> None:
        calls = signal_recorder(signals.member_reactivated)
        member = ProfileUserRoleFactory()
        deactivate_member(member, by=UserFactory())

        with django_capture_on_commit_callbacks(execute=True):
            reactivate_member(member)

        member.refresh_from_db()
        assert member.status == Status.ACTIVE
        assert member.deactivated_at is None
        assert member.deactivated_by is None
        assert len(calls) == 1

    def test_only_deactivated_members_can_be_reactivated(self) -> None:
        with pytest.raises(ProfileMembershipError) as excinfo:
            reactivate_member(ProfileUserRoleFactory())
        assert excinfo.value.code == "invalid_status"

    def test_role_change_reports_old_and_new_role(
        self, signal_recorder, django_capture_on_commit_callbacks
    ) -> None:
        calls = signal_recorder(signals.member_role_changed)
        by = UserFactory()
        member = ProfileUserRoleFactory(role=MANAGER)

        with django_capture_on_commit_callbacks(execute=True):
            change_member_role(member, ADMIN, by=by)
            change_member_role(member, ADMIN, by=by)  # no change, no signal

        assert len(calls) == 1
        assert (calls[0]["old_role"], calls[0]["new_role"], calls[0]["by"]) == (
            MANAGER,
            ADMIN,
            by,
        )

    def test_an_unassignable_role_is_refused(self) -> None:
        with pytest.raises(ProfileMembershipError) as excinfo:
            change_member_role(ProfileUserRoleFactory(), 99)
        assert excinfo.value.code == "invalid_input"

    def test_remove_reports_the_former_primary_key(
        self, signal_recorder, django_capture_on_commit_callbacks
    ) -> None:
        calls = signal_recorder(signals.member_removed)
        member = ProfileUserRoleFactory()
        pk = member.pk

        with django_capture_on_commit_callbacks(execute=True):
            remove_member(member)

        assert not ProfileUserRole.objects.filter(pk=pk).exists()
        assert calls[0]["pk"] == pk


class TestProjectRoles:
    """A project extends the roles by redeclaring `ProfileRoles` on its concrete model."""

    def test_the_default_roles_are_unchanged(self) -> None:
        field = ProfileUserRole._meta.get_field("role")
        assert list(field.choices) == list(ProfileUserRole.ProfileRoles.choices)
        assert set(ProfileUserRole.ProfileRoles.values) == {ADMIN, MANAGER}

    @isolate_apps("baseapp_profiles")
    def test_redeclared_roles_reach_the_role_field(self) -> None:
        class ProjectProfileUserRole(AbstractProfileUserRole):
            class ProfileRoles(models.IntegerChoices):
                ADMIN = 1, "admin"
                MANAGER = 2, "manager"
                VIEWER = 3, "viewer"

            class Meta(AbstractProfileUserRole.Meta):
                app_label = "baseapp_profiles"

        field = ProjectProfileUserRole._meta.get_field("role")
        assert (3, "viewer") in field.choices
        assert 3 in ProjectProfileUserRole.assignable_roles()
        # What get_role_display() and the admin read.
        assert dict(field.flatchoices)[3] == "viewer"

    @isolate_apps("baseapp_profiles")
    def test_full_clean_accepts_a_redeclared_role(self) -> None:
        class ProjectProfileUserRole(AbstractProfileUserRole):
            class ProfileRoles(models.IntegerChoices):
                ADMIN = 1, "admin"
                MANAGER = 2, "manager"
                VIEWER = 3, "viewer"

            class Meta(AbstractProfileUserRole.Meta):
                app_label = "baseapp_profiles"

        # What `full_clean()` runs on the column (the model itself cannot be instantiated
        # here: its relations point at models outside the isolated registry).
        field = ProjectProfileUserRole._meta.get_field("role")
        assert field.clean(3, None) == 3
        with pytest.raises(ValidationError):
            field.clean(4, None)

    def test_the_apis_read_the_concrete_models_roles(self) -> None:
        # A project's redeclared `ProfileRoles` lives on the concrete model, so this is what
        # puts its roles into the GraphQL enum and the REST serializers.
        assert ProfileRoleTypesEnum._meta.enum is ProfileUserRole.ProfileRoles
        for serializer in (ProfileMemberRoleSerializer(), ProfileInvitationSendSerializer()):
            assert list(serializer.fields["role"].choices) == list(
                ProfileUserRole.ProfileRoles.values
            )

    def test_roles_held_back_by_assignable_roles_are_refused(self, monkeypatch) -> None:
        member = ProfileUserRoleFactory(role=ADMIN)
        monkeypatch.setattr(ProfileUserRole, "assignable_roles", classmethod(lambda cls: [ADMIN]))

        validate_role(ADMIN)
        with pytest.raises(ProfileMembershipError) as excinfo:
            change_member_role(member, MANAGER)
        assert excinfo.value.code == "invalid_input"
        serializer = ProfileMemberRoleSerializer(data={"role": MANAGER})
        assert not serializer.is_valid()
