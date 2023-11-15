import baseapp_auth.tests.helpers as h
import pytest
from baseapp_auth.rest_framework.users.serializers import UserSerializer
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from rest_framework import viewsets
from rest_framework.settings import api_settings

pytestmark = pytest.mark.django_db

User = get_user_model()
UserFactory = h.get_user_factory()


class TestPagination:
    class TestModelViewSet(viewsets.ModelViewSet):
        permission_classes = []
        serializer_class = UserSerializer

        def get_queryset(self):
            return User.objects.all()

    def test_uses_page_size_query_param(self):
        expected_page_size = 5
        UserFactory.create_batch(size=expected_page_size + 1)
        self.factory = RequestFactory()

        request = self.factory.get("", {"page_size": expected_page_size})
        response = self.TestModelViewSet.as_view({"get": "list"})(request)
        h.responseOk(response)
        assert len(response.data["results"]) == expected_page_size

    def test_uses_page_size_setting_by_default(self):
        UserFactory.create_batch(size=api_settings.PAGE_SIZE + 1)
        self.factory = RequestFactory()

        request = self.factory.get("")
        response = self.TestModelViewSet.as_view({"get": "list"})(request)
        h.responseOk(response)
        assert len(response.data["results"]) == api_settings.PAGE_SIZE
