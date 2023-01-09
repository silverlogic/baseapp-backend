import pytest
from django.urls import include, path, reverse
from rest_framework import decorators, response, status, viewsets
from rest_framework.routers import DefaultRouter
from rest_framework.test import APITestCase, URLPatternsTestCase
from django.contrib.auth.models import Permission

from drf_view_action_permissions.action import DjangoActionPermissions
from testproject.testapp.models import TestModel

from . import factories as f
from . import helpers as h
from .fixtures import Client

pytestmark = pytest.mark.django_db

def check_user_permission(user, view, obj=None):
    return user.has_perm('testapp.list_tests')

def check_object_permission(user, view, obj=None):
    if not obj:
        return True
    return obj.title == 'verified'


class DummyViewSet(viewsets.GenericViewSet):
    permission_classes = [DjangoActionPermissions, ]
    queryset = TestModel.objects.all()
    permission_base = "testmodel"
    perms_map_action = {
        "disable": ['testapp.test_disable'],
        "method_check": [check_user_permission],
        "object_check": [check_object_permission],
        "multi_perms": [check_user_permission, 'testapp.view_testmodel', 'testapp.add_testmodel'],
    }

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

    @decorators.action(methods=["POST"], detail=True)
    def disable(self, *args, **kwargs):
        return response.Response({})

    @decorators.action(methods=["POST"], detail=True)
    def object_check(self, request, pk=None):
        self.get_object()
        return response.Response({})

    @decorators.action(methods=["GET"], detail=False)
    def method_check(self, *args, **kwargs):
        return response.Response({})

    @decorators.action(methods=["GET"], detail=False)
    def multi_perms(self, *args, **kwargs):
        return response.Response({})


class TestActionPermission(APITestCase, URLPatternsTestCase):
    client_class = Client
    test_router = DefaultRouter(trailing_slash=False)
    test_router.register(r"test", DummyViewSet, basename="test")

    urlpatterns = [
        path("/", include(test_router.urls)),
    ]

    def setUp(self) -> None:
        f.TestModelFactory()
        return super().setUp()

    def test_cannot_access_create_in_viewset(self):
        role = f.RoleFactory()
        user = f.UserFactory(role=role)
        self.client.force_authenticate(user)

        r = self.client.post(reverse("test-list"))
        h.responseForbidden(r)
        
    def test_can_access_create_in_viewset_with_perms(self):
        role = f.RoleFactory()
        permission = Permission.objects.filter(codename='add_testmodel').first()
        role.permissions.add(permission)
        user = f.UserFactory(role=role)
        self.client.force_authenticate(user)

        r = self.client.post(reverse("test-list"))
        h.responseCreated(r)

    def test_can_access_update_in_viewset_with_perms(self):
        role = f.RoleFactory()
        permission = Permission.objects.filter(codename='change_testmodel').first()
        role.permissions.add(permission)
        user = f.UserFactory(role=role)
        self.client.force_authenticate(user)

        r = self.client.put(reverse("test-detail", kwargs={"pk": 0}))
        h.responseOk(r)
        
    def test_cannot_access_update_in_viewset_without_perms(self):
        user = f.UserFactory()
        self.client.force_authenticate(user)

        r = self.client.put(reverse("test-detail", kwargs={"pk": 0}))
        h.responseForbidden(r)
    
    def test_can_access_retrieve_in_viewset_with_perms(self):
        role = f.RoleFactory()
        test = f.TestModelFactory()
        permission = Permission.objects.filter(codename='view_testmodel').first()
        role.permissions.add(permission)
        user = f.UserFactory(role=role)
        self.client.force_authenticate(user)

        r = self.client.get(reverse("test-detail", kwargs={"pk": test.id}))
        h.responseOk(r)
        
    def test_cannot_access_retrieve_in_viewset_without_perms(self):
        role = f.RoleFactory()
        user = f.UserFactory(role=role)
        self.client.force_authenticate(user)

        r = self.client.get(reverse("test-detail", kwargs={"pk": 0}))
        h.responseForbidden(r)
    
    def test_can_access_destroy_in_viewset_with_perms(self):
        role = f.RoleFactory()
        permission = Permission.objects.filter(codename='delete_testmodel').first()
        role.permissions.add(permission)
        user = f.UserFactory(role=role)
        self.client.force_authenticate(user)

        r = self.client.delete(reverse("test-detail", kwargs={"pk": 0}))
        h.responseNoContent(r)
        
    def test_cannot_access_destroy_in_viewset_without_perms(self):
        role = f.RoleFactory()
        user = f.UserFactory(role=role)
        self.client.force_authenticate(user)

        r = self.client.delete(reverse("test-detail", kwargs={"pk": 0}))
        h.responseForbidden(r)
        
    def test_can_access_list_in_viewset_with_perms(self):
        role = f.RoleFactory()
        permission = Permission.objects.filter(codename='view_testmodel_list').first()
        role.permissions.add(permission)
        user = f.UserFactory(role=role)
        self.client.force_authenticate(user)

        r = self.client.get(reverse("test-list"))
        h.responseOk(r)
        
    def test_cannot_access_list_in_viewset_without_perms(self):
        role = f.RoleFactory()
        user = f.UserFactory(role=role)
        self.client.force_authenticate(user)

        r = self.client.get(reverse("test-list"))
        h.responseForbidden(r)
        
    def test_can_access_custom_action_in_viewset_with_perms(self):
        role = f.RoleFactory()
        
        permission = Permission.objects.filter(codename='custom_action_testmodel').first()
        role.permissions.add(permission)
        user = f.UserFactory(role=role)
        self.client.force_authenticate(user)

        r = self.client.get(reverse("test-custom-action"))
        h.responseOk(r)
        
    def test_cannot_access_custom_action_in_viewset_without_perms(self):
        role = f.RoleFactory()
        user = f.UserFactory(role=role)
        self.client.force_authenticate(user)

        r = self.client.get(reverse("test-custom-action"))
        h.responseForbidden(r)
        
    def test_can_access_custom_detail_action_in_viewset_with_perms(self):
        role = f.RoleFactory()
        permission = Permission.objects.filter(codename='custom_detail_action_testmodel').first()
        role.permissions.add(permission)
        user = f.UserFactory(role=role)
        self.client.force_authenticate(user)

        r = self.client.patch(reverse("test-custom-detail-action", kwargs={"pk": 0}))
        h.responseOk(r)
        
    def test_cannot_access_custom_detail_action_in_viewset_without_perms(self):
        role = f.RoleFactory()
        user = f.UserFactory(role=role)
        self.client.force_authenticate(user)

        r = self.client.patch(reverse("test-custom-detail-action", kwargs={"pk": 0}))
        h.responseForbidden(r)

    def test_can_access_disable_in_viewset_with_perms(self):
        role = f.RoleFactory()
        permission = Permission.objects.filter(codename='test_disable').first()
        role.permissions.add(permission)
        user = f.UserFactory(role=role)
        self.client.force_authenticate(user)

        r = self.client.post(reverse("test-disable", kwargs={"pk": 0}))
        h.responseOk(r)
        
    def test_cannot_access_disable_in_viewset_without_perms(self):
        role = f.RoleFactory()
        user = f.UserFactory(role=role)
        self.client.force_authenticate(user)

        r = self.client.post(reverse("test-disable", kwargs={"pk": 0}))
        h.responseForbidden(r)

    def test_can_access_object_check_in_viewset(self):
        test = f.TestModelFactory(title="verified")
        user = f.UserFactory()
        self.client.force_authenticate(user)

        r = self.client.post(reverse("test-object-check", kwargs={"pk": test.id}))
        h.responseOk(r)
        
    def test_cannot_access_object_check_in_viewset(self):
        role = f.RoleFactory()
        user = f.UserFactory(role=role)
        test = f.TestModelFactory()
        self.client.force_authenticate(user)

        r = self.client.post(reverse("test-object-check", kwargs={"pk": test.id}))
        h.responseForbidden(r)

    def test_can_access_method_check_in_viewset_with_perms(self):
        role = f.RoleFactory()
        permission = Permission.objects.filter(codename='list_tests').first()
        role.permissions.add(permission)
        user = f.UserFactory(role=role)
        self.client.force_authenticate(user)

        r = self.client.get(reverse("test-method-check"))
        h.responseOk(r)
        
    def test_cannot_access_method_check_in_viewset_without_perms(self):
        user = f.UserFactory()
        self.client.force_authenticate(user)

        r = self.client.get(reverse("test-method-check"))
        h.responseForbidden(r)

    def test_can_access_multi_perms_in_viewset_with_perms(self):
        role = f.RoleFactory()
        permission_1 = Permission.objects.filter(codename='list_tests').first()
        permission_2 = Permission.objects.filter(codename='view_testmodel').first()
        permission_3 = Permission.objects.filter(codename='add_testmodel').first()
        role.permissions.add(permission_1)
        role.permissions.add(permission_2)
        role.permissions.add(permission_3)
        user = f.UserFactory(role=role)
        self.client.force_authenticate(user)

        r = self.client.get(reverse("test-multi-perms"))
        h.responseOk(r)
        
    def test_cannot_access_multi_perms_in_viewset_without_perms(self):
        role = f.RoleFactory()
        permission_1 = Permission.objects.filter(codename='list_tests').first()
        permission_2 = Permission.objects.filter(codename='view_testmodel').first()
        role.permissions.add(permission_1)
        role.permissions.add(permission_2)
        user = f.UserFactory(role=role)
        self.client.force_authenticate(user)

        r = self.client.get(reverse("test-multi-perms"))
        h.responseForbidden(r)

