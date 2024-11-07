import baseapp_auth.tests.helpers as h
import pytest
from baseapp_auth.tests.mixins import ApiMixin
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
