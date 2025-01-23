import baseapp_auth.tests.helpers as h
import pytest
from baseapp_auth.tests.mixins import ApiMixin
from baseapp_devices.models import UserDevice
from baseapp_devices.tests.factories import UserDeviceFactory
from rest_framework_simplejwt.tokens import RefreshToken

pytestmark = pytest.mark.django_db

UserFactory = h.get_user_factory()


class TestJwtRefresh(ApiMixin):
    login_endpoint_path = "/v1/auth/jwt/refresh"

    def test_receives_new_access_token(self, client):
        user = UserFactory()
        refresh = RefreshToken.for_user(user)
        refresh_token = str(refresh)
        r = client.post(self.login_endpoint_path, {"refresh": refresh_token})
        h.responseOk(r)
        assert set(r.data.keys()) == {"access"}


class TestJwtLogoutDevice(ApiMixin):
    view_path = "/v1/auth/jwt/logoutdevice"

    def test_user_can_logout_device(self, client):
        user = UserFactory()
        refresh = RefreshToken.for_user(user)
        refresh_token = str(refresh)
        device = UserDeviceFactory(user=user, device_id="123", device_token=refresh_token)
        r = client.post(self.view_path, {"device_id": device.device_id})
        h.responseOk(r)
        assert r.data["message"] == "Device logged out successfully"
        assert not UserDevice.objects.filter(device_id=device.device_id).exists()
