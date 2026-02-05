import pytest
from cryptography import exceptions as cryptography_exceptions
from django.conf import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.urls import include, path, reverse
from django.utils import timezone
from freezegun import freeze_time
from rest_framework import decorators, response, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.routers import DefaultRouter
from rest_framework.test import APITestCase, URLPatternsTestCase

import baseapp_api_key.tests.factories as f
from baseapp_api_key.models import APIKey
from baseapp_api_key.rest_framework.permissions import HasAPIKey
from baseapp_core.tests import helpers as h
from baseapp_core.tests.fixtures import Client

pytestmark = pytest.mark.django_db


class TestAPIKey(TestCase):
    def test_is_expired_when_expiry_date_is_null(self):
        api_key = f.APIKeyFactory()

        assert APIKey.objects.get(pk=api_key.pk).is_expired is False

        with freeze_time((timezone.now() + timezone.timedelta(days=1)).strftime("%Y-%m-%d")):
            assert APIKey.objects.get(pk=api_key.pk).is_expired is False

    def test_is_expired_when_expiry_date_is_set(self):
        api_key = f.APIKeyFactory(expiry_date=timezone.now() + timezone.timedelta(days=1))

        assert APIKey.objects.get(pk=api_key.pk).is_expired is False

        with freeze_time((timezone.now() + timezone.timedelta(days=1)).strftime("%Y-%m-%d")):
            assert APIKey.objects.get(pk=api_key.pk).is_expired is True

    @override_settings(
        BA_API_KEY_ENCRYPTION_KEY="jCe8USiQJDatFT5T0WCIl86QBxYs0-Q7iDJQc77Dh7LR1VAnWW3PA9UyXK-V7LhFnKq9sLd3xDw5FTrrYYtj2Q=="
    )
    def test_can_rotate_encryption_key(self):
        BA_API_KEY_ENCRYPTION_KEY_OLD = APIKey.objects.generate_encryption_key()
        BA_API_KEY_ENCRYPTION_KEY_NEW = APIKey.objects.generate_encryption_key()

        with override_settings(BA_API_KEY_ENCRYPTION_KEY=BA_API_KEY_ENCRYPTION_KEY_OLD):
            api_key = f.APIKeyFactory(expiry_date=timezone.now() + timezone.timedelta(days=1))
            unencrypted_api_key_old = APIKey.objects.decrypt(
                encrypted_value=api_key.encrypted_api_key
            )

            APIKey.objects.rotate_encryption_key(
                encryption_key_old=BA_API_KEY_ENCRYPTION_KEY_OLD,
                encryption_key_new=BA_API_KEY_ENCRYPTION_KEY_NEW,
            )

            api_key.refresh_from_db()

            # Test decrypt succeeds with BA_API_KEY_ENCRYPTION_KEY_NEW
            with override_settings(BA_API_KEY_ENCRYPTION_KEY=BA_API_KEY_ENCRYPTION_KEY_NEW):
                unencrypted_api_key_new = APIKey.objects.decrypt(
                    encrypted_value=api_key.encrypted_api_key
                )
                assert unencrypted_api_key_old == unencrypted_api_key_new

            # Test decrypt fails with BA_API_KEY_ENCRYPTION_KEY_OLD
            with self.assertRaises(
                (
                    cryptography_exceptions.InvalidTag,
                    cryptography_exceptions.InvalidKey,
                    cryptography_exceptions.InvalidSignature,
                )
            ):
                APIKey.objects.decrypt(encrypted_value=api_key.encrypted_api_key)

    def test_encrypt_raises_if_encryption_key_not_set(self):
        with override_settings(BA_API_KEY_ENCRYPTION_KEY=None):
            with self.assertRaises(ImproperlyConfigured) as excinfo:
                APIKey.objects.encrypt("some-value")
            assert "BA_API_KEY_ENCRYPTION_KEY is not set" in str(excinfo.exception)

    def test_decrypt_raises_if_encryption_key_not_set(self):
        with override_settings(BA_API_KEY_ENCRYPTION_KEY=None):
            with self.assertRaises(ImproperlyConfigured) as excinfo:
                APIKey.objects.decrypt(b"00")
            assert "BA_API_KEY_ENCRYPTION_KEY is not set" in str(excinfo.exception)

    def test_rotate_encryption_key_raises_if_encryption_key_not_set(self):
        with override_settings(
            BA_API_KEY_ENCRYPTION_KEY="jCe8USiQJDatFT5T0WCIl86QBxYs0-Q7iDJQc77Dh7LR1VAnWW3PA9UyXK-V7LhFnKq9sLd3xDw5FTrrYYtj2Q=="
        ):
            f.APIKeyFactory()
        with override_settings(BA_API_KEY_ENCRYPTION_KEY=None):
            with self.assertRaises(ImproperlyConfigured) as excinfo:
                APIKey.objects.rotate_encryption_key(
                    encryption_key_old=None,
                    encryption_key_new=None,
                )
            assert "BA_API_KEY_ENCRYPTION_KEY is not set" in str(excinfo.exception)


class TestAPIKeyAuthentication(APITestCase, URLPatternsTestCase):
    class DummyViewSet(viewsets.GenericViewSet):
        @decorators.action(
            methods=["POST"],
            detail=False,
            permission_classes=[
                IsAuthenticated,
            ],
        )
        def custom_action(self, *args, **kwargs):
            return response.Response({})

    client_class = Client
    test_router = DefaultRouter(trailing_slash=False)
    test_router.register(r"dummy", DummyViewSet, basename="dummy")

    urlpatterns = [
        path("/", include(test_router.urls)),
    ]

    def test_missing_api_key(self):
        r = self.client.post(reverse("dummy-custom-action"), {})
        h.responseUnauthorized(r)

    def test_has_non_expired_api_key(self):
        api_key = f.APIKeyFactory()
        unencrypted_api_key = APIKey.objects.decrypt(encrypted_value=api_key.encrypted_api_key)

        r = self.client.post(
            path=reverse("dummy-custom-action"),
            data={},
            headers=dict(API_KEY=unencrypted_api_key),
        )
        h.responseOk(r)

    def test_has_expired_api_key(self):
        api_key = f.APIKeyFactory(expiry_date=timezone.now() + timezone.timedelta(days=1))
        unencrypted_api_key = APIKey.objects.decrypt(encrypted_value=api_key.encrypted_api_key)

        with freeze_time((timezone.now() + timezone.timedelta(days=1)).strftime("%Y-%m-%d")):
            r = self.client.post(
                path=reverse("dummy-custom-action"),
                data={},
                headers=dict(API_KEY=unencrypted_api_key),
            )
            h.responseUnauthorized(r)


class TestHasAPIKeyPermission(APITestCase, URLPatternsTestCase):
    class DummyViewSet(viewsets.GenericViewSet):
        @decorators.action(
            methods=["POST"],
            detail=False,
            permission_classes=[
                HasAPIKey,
            ],
        )
        def custom_action(self, *args, **kwargs):
            return response.Response({})

    client_class = Client
    test_router = DefaultRouter(trailing_slash=False)
    test_router.register(r"dummy", DummyViewSet, basename="dummy")

    urlpatterns = [
        path("/", include(test_router.urls)),
    ]

    def test_missing_api_key(self):
        r = self.client.post(reverse("dummy-custom-action"), {})
        h.responseUnauthorized(r)

    def test_has_non_expired_api_key(self):
        api_key = f.APIKeyFactory()
        unencrypted_api_key = APIKey.objects.decrypt(encrypted_value=api_key.encrypted_api_key)

        r = self.client.post(
            path=reverse("dummy-custom-action"),
            data={},
            headers=dict(API_KEY=unencrypted_api_key),
        )
        h.responseOk(r)

    def test_has_expired_api_key(self):
        api_key = f.APIKeyFactory(expiry_date=timezone.now() + timezone.timedelta(days=1))
        unencrypted_api_key = APIKey.objects.decrypt(encrypted_value=api_key.encrypted_api_key)

        with freeze_time((timezone.now() + timezone.timedelta(days=1)).strftime("%Y-%m-%d")):
            r = self.client.post(
                path=reverse("dummy-custom-action"),
                data={},
                headers=dict(API_KEY=unencrypted_api_key),
            )
            h.responseUnauthorized(r)
