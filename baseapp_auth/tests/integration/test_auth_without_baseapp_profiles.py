import pytest
from django.urls import reverse
from rest_framework_simplejwt.authentication import JWTAuthentication

from baseapp_core.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

ME_WITH_PROFILE_COUPLED_FIELDS_GRAPHQL = """
    query {
        me {
            fullName
            avatar(width: 32, height: 32) {
                url
            }
        }
    }
"""


@pytest.mark.parametrize("with_disabled_apps", [["baseapp_profiles"]], indirect=True)
class TestAuthWithoutBaseappProfiles:
    @staticmethod
    def _detach_profile_if_present(user):
        if hasattr(user, "profile_id"):
            user.profile_id = None
            user.save(update_fields=["profile"])

    def test_user_retrieve_works_without_profiles(self, with_disabled_apps, user_client):
        self._detach_profile_if_present(user_client.user)
        response = user_client.get(reverse("v1:users-detail", kwargs={"pk": user_client.user.pk}))

        assert response.status_code == 200
        assert "profile" in response.data
        assert response.data["profile"] is None

    def test_user_can_update_avatar_without_profiles(
        self, with_disabled_apps, user_client, image_base64
    ):
        self._detach_profile_if_present(user_client.user)
        response = user_client.patch(
            reverse("v1:users-detail", kwargs={"pk": user_client.user.pk}),
            {"avatar": image_base64},
        )

        assert response.status_code == 200
        assert "profile" in response.data
        assert response.data["profile"] is None

    def test_jwt_login_does_not_require_profiles(self, with_disabled_apps, client):
        password = "1234567890"
        user = UserFactory(email="without-profiles@example.com", password=password)
        self._detach_profile_if_present(user)

        response = client.post(
            "/v1/auth/jwt/login",
            {"email": user.email, "password": password},
        )

        assert response.status_code == 200
        assert set(response.data.keys()) == {"access", "refresh"}

        validated_token = JWTAuthentication().get_validated_token(response.data["access"])
        assert validated_token["id"] == str(user.public_id)
        assert validated_token["email"] == user.email
        assert "profile" not in validated_token or validated_token["profile"] is None

    def test_me_query_uses_safe_fallbacks_for_full_name_and_avatar_without_profiles(
        self,
        with_disabled_apps,
        django_user_client,
        graphql_user_client,
    ):
        self._detach_profile_if_present(django_user_client.user)

        response = graphql_user_client(ME_WITH_PROFILE_COUPLED_FIELDS_GRAPHQL)
        content = response.json()

        assert "errors" not in content
        assert content["data"]["me"]["fullName"] == django_user_client.user.get_full_name()
        assert content["data"]["me"]["avatar"] is None
