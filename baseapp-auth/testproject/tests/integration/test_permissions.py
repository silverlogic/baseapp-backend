from django.urls import include, path, reverse

import pytest
from rest_framework import decorators, response, status, viewsets
from rest_framework.test import APITestCase, URLPatternsTestCase

from apps.api.v1.router import DefaultRouter
from apps.api.v1.users.permissions import ActionPermission

import tests.factories as f
import tests.helpers as h
from tests.fixtures import Client

pytestmark = pytest.mark.django_db


class TestUserPermissions:
    def test_get_permissions_directly_assigned_to_role(self):
        permissions = f.PermissionFactory.create_batch(size=3)
        role = f.RoleFactory(permissions=permissions)
        user = f.UserFactory(role=role)

        assert set(user.permissions) == set([p.slug for p in permissions])

    def test_get_permissions_from_permission_groups_in_role(self):
        permissions_group_0 = f.PermissionFactory.create_batch(size=3)
        permissions_group_1 = f.PermissionFactory.create_batch(size=2)
        role = f.RoleFactory(
            permission_groups=[
                f.PermissionGroupFactory(permissions=permissions_group_0),
                f.PermissionGroupFactory(permissions=permissions_group_1),
            ]
        )
        user = f.UserFactory(role=role)

        assert set(user.permissions) == set(
            [p.slug for p in permissions_group_0] + [p.slug for p in permissions_group_1]
        )

    def test_get_permissions_from_permission_groups_directly_assigned_to_user(self):
        permissions_group_0 = f.PermissionFactory.create_batch(size=1)
        permissions_group_1 = f.PermissionFactory.create_batch(size=4)
        permission_groups = [
            f.PermissionGroupFactory(permissions=permissions_group_0),
            f.PermissionGroupFactory(permissions=permissions_group_1),
        ]
        user = f.UserFactory(permission_groups=permission_groups)

        assert set(user.permissions) == set(
            [p.slug for p in permissions_group_0] + [p.slug for p in permissions_group_1]
        )

    def test_exclude_permissions_for_role(self):
        permissions_for_group = f.PermissionFactory.create_batch(size=3)
        single_permission = f.PermissionFactory()
        role = f.RoleFactory(
            permission_groups=[f.PermissionGroupFactory(permissions=permissions_for_group)],
            permissions=[single_permission],
            exclude_permissions=[permissions_for_group[2]],
        )

        user = f.UserFactory(role=role)
        assert set(user.permissions) == set(
            [p.slug for p in permissions_for_group[:2]] + [single_permission.slug]
        )


class DummyViewSet(viewsets.GenericViewSet):
    permission_classes = [ActionPermission]
    permission_base = "test_dummy"

    def create(self, *args, **kwargs):
        return response.Response({}, status=status.HTTP_201_CREATED)

    def list(self, *args, **kwargs):
        return response.Response([])

    def retrieve(self, *args, **kwargs):
        return response.Response({})

    def update(self, *args, **kwargs):
        return response.Response({})

    def partial_update(self, *args, **kwargs):
        return response.Response({})

    def destroy(self, *args, **kwargs):
        return response.Response({}, status=status.HTTP_204_NO_CONTENT)

    @decorators.action(methods=["GET"], detail=False)
    def custom_action(self, *args, **kwargs):
        return response.Response({})

    @decorators.action(methods=["PATCH"], detail=True)
    def custom_detail_action(self, *args, **kwargs):
        return response.Response({})


class TestActionPermission(APITestCase, URLPatternsTestCase):
    client_class = Client
    test_router = DefaultRouter(trailing_slash=False)
    test_router.register(r"test", DummyViewSet, basename="test")

    urlpatterns = [
        path("/", include(test_router.urls)),
    ]

    def test_restrict_access_to_default_actions_in_viewset(self):
        role = f.RoleFactory()
        user = f.UserFactory(role=role)
        self.client.force_authenticate(user)

        # Create
        r = self.client.post(reverse("test-list"))
        h.responseForbidden(r)

        create_permission = f.PermissionFactory(name="Test Dummy Create")
        role.permissions.add(create_permission)
        r = self.client.post(reverse("test-list"))
        h.responseCreated(r)

        # List
        r = self.client.get(reverse("test-list"))
        h.responseForbidden(r)

        list_permission = f.PermissionFactory(name="Test Dummy List")
        role.permissions.add(list_permission)
        r = self.client.get(reverse("test-list"))
        h.responseOk(r)

        # Retrieve
        r = self.client.get(reverse("test-detail", kwargs={"pk": 0}))
        h.responseForbidden(r)

        retrieve_permission = f.PermissionFactory(name="Test Dummy Retrieve")
        role.permissions.add(retrieve_permission)
        r = self.client.get(reverse("test-detail", kwargs={"pk": 0}))
        h.responseOk(r)

        # Update
        r = self.client.put(reverse("test-detail", kwargs={"pk": 0}))
        h.responseForbidden(r)
        r = self.client.patch(reverse("test-detail", kwargs={"pk": 0}))
        h.responseForbidden(r)

        update_permission = f.PermissionFactory(name="Test Dummy Update")
        role.permissions.add(update_permission)
        r = self.client.put(reverse("test-detail", kwargs={"pk": 0}))
        h.responseOk(r)
        r = self.client.patch(reverse("test-detail", kwargs={"pk": 0}))
        h.responseOk(r)

        # Destroy
        r = self.client.delete(reverse("test-detail", kwargs={"pk": 0}))
        h.responseForbidden(r)

        destroy_permission = f.PermissionFactory(name="Test Dummy Destroy")
        role.permissions.add(destroy_permission)
        r = self.client.delete(reverse("test-detail", kwargs={"pk": 0}))
        h.responseNoContent(r)

    def test_restrict_access_to_custom_action_in_viewset(self):
        role = f.RoleFactory()
        user = f.UserFactory(role=role)
        self.client.force_authenticate(user)

        r = self.client.get(reverse("test-custom-action"))
        h.responseForbidden(r)

        list_permission = f.PermissionFactory(name="Test Dummy Custom Action List")
        role.permissions.add(list_permission)
        r = self.client.get(reverse("test-custom-action"))
        h.responseOk(r)

        r = self.client.patch(reverse("test-custom-detail-action", kwargs={"pk": 0}))
        h.responseForbidden(r)

        update_permission = f.PermissionFactory(name="Test Dummy Custom Detail Action Update")
        role.permissions.add(update_permission)
        r = self.client.patch(reverse("test-custom-detail-action", kwargs={"pk": 0}))
        h.responseOk(r)
