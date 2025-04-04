import pytest
from django.contrib.auth.models import Permission

from . import factories as f

pytestmark = pytest.mark.django_db


class TestUserPermissions:
    def test_get_permissions_directly_assigned_to_role(self):
        permission_1 = Permission.objects.filter(codename="list_tests").first()
        permission_2 = Permission.objects.filter(codename="test_disable").first()
        permissions = [permission_1, permission_2]
        role = f.RoleFactory(permissions=permissions)
        user = f.UserFactory(role=role)

        assert user.permission_list == set(
            [f"{p.content_type.app_label}.{p.codename}" for p in permissions]
        )

    def test_get_permissions_from_permission_groups_in_role(self):
        permission_1 = Permission.objects.filter(codename="list_tests").first()
        permission_2 = Permission.objects.filter(codename="test_disable").first()
        role = f.RoleFactory(
            groups=[
                f.GroupFactory(permissions=[permission_1]),
                f.GroupFactory(permissions=[permission_2]),
            ]
        )
        user = f.UserFactory(role=role)

        assert user.permission_list == set(
            [
                f"{permission_1.content_type.app_label}.{permission_1.codename}",
                f"{permission_2.content_type.app_label}.{permission_2.codename}",
            ]
        )

    def test_get_permissions_from_permission_groups_directly_assigned_to_user(self):
        permission_1 = Permission.objects.filter(codename="list_tests").first()
        permission_2 = Permission.objects.filter(codename="test_disable").first()
        permission_groups = [
            f.GroupFactory(permissions=[permission_1]),
            f.GroupFactory(permissions=[permission_2]),
        ]
        user = f.UserFactory(groups=permission_groups)

        assert user.permission_list == set(
            [
                f"{permission_1.content_type.app_label}.{permission_1.codename}",
                f"{permission_2.content_type.app_label}.{permission_2.codename}",
            ]
        )

    def test_exclude_permissions_for_role(self):
        permission_1 = Permission.objects.filter(codename="list_tests").first()
        permission_2 = Permission.objects.filter(codename="test_disable").first()
        role = f.RoleFactory(
            groups=[f.GroupFactory(permissions=[permission_1])],
            permissions=[permission_2],
            exclude_permissions=[permission_1],
        )

        user = f.UserFactory(role=role)
        assert user.permission_list == set(
            [f"{permission_2.content_type.app_label}.{permission_2.codename}"]
        )

    def test_user_has_perms(self):
        permission_1 = Permission.objects.filter(codename="list_tests").first()
        permission_2 = Permission.objects.filter(codename="test_disable").first()
        permissions = [permission_1, permission_2]
        role = f.RoleFactory(permissions=permissions)
        user = f.UserFactory(role=role)

        assert user.has_perm("baseapp_drf_view_action_permissions_tests.list_tests")
        assert user.has_perms(
            [
                "baseapp_drf_view_action_permissions_tests.list_tests",
                "baseapp_drf_view_action_permissions_tests.test_disable",
            ]
        )

    def test_user_has_perms_override_for_super_user(self):
        user = f.UserFactory(is_superuser=True)
        assert user.has_perm("baseapp_drf_view_action_permissions_tests.list_tests")
        assert user.has_perms(
            [
                "baseapp_drf_view_action_permissions_tests.list_tests",
                "baseapp_drf_view_action_permissions_tests.test_disable",
            ]
        )
