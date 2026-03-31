import pytest
from django.urls import include, path, reverse
from django.utils import timezone
from rest_framework.routers import DefaultRouter
from rest_framework.test import APITestCase, URLPatternsTestCase

from baseapp_api_key.models import APIKey
from baseapp_api_key.rest_framework.views import APIKeyViewSet
from baseapp_auth.tests.helpers import get_user_factory
from baseapp_core.tests import helpers as h
from baseapp_core.tests.fixtures import Client

pytestmark = pytest.mark.django_db


class TestAPIKeyViewSet(APITestCase, URLPatternsTestCase):
    class DefaultExpiryAPIKeyViewSet(APIKeyViewSet):
        pass

    class NonExpiringAPIKeyViewSet(APIKeyViewSet):
        expiry_time_seconds = None

    client_class = Client
    test_router = DefaultRouter(trailing_slash=False)
    test_router.register(
        r"api-keys-default", DefaultExpiryAPIKeyViewSet, basename="api-keys-default"
    )
    test_router.register(
        r"api-keys-no-expiry", NonExpiringAPIKeyViewSet, basename="api-keys-no-expiry"
    )

    urlpatterns = [
        path("/", include(test_router.urls)),
    ]

    def setUp(self):
        self.user = get_user_factory()()
        self.client.force_authenticate(self.user)

    def test_create_uses_default_expiry_and_returns_key(self):
        response = self.client.post(reverse("api-keys-default-list"), {})

        h.responseOk(response)
        assert response.data["expires_in_seconds"] == 3600

        encrypted_api_key = APIKey.objects.encrypt(response.data["api_key"])
        api_key = APIKey.objects.get(encrypted_api_key=encrypted_api_key)

        assert api_key.user_id == self.user.id
        assert api_key.name == "auto-generated-key"
        assert api_key.expiry_date is not None

        now = timezone.now()
        expected_expiry = now + timezone.timedelta(seconds=3600)
        assert abs((api_key.expiry_date - expected_expiry).total_seconds()) < 5

    def test_create_with_no_expiry_sets_null_expiry_date(self):
        response = self.client.post(reverse("api-keys-no-expiry-list"), {})

        h.responseOk(response)
        assert response.data["expires_in_seconds"] is None

        encrypted_api_key = APIKey.objects.encrypt(response.data["api_key"])
        api_key = APIKey.objects.get(encrypted_api_key=encrypted_api_key)

        assert api_key.user_id == self.user.id
        assert api_key.name == "auto-generated-key"
        assert api_key.expiry_date is None
