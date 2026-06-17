from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from baseapp_social_auth.tests.pipeline import set_avatar

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("with_disabled_apps", [["baseapp_profiles"]], indirect=True)
class TestSocialAuthPipelineWithoutBaseappProfiles:
    def test_set_avatar_does_not_require_profile_attribute_when_profiles_disabled(
        self,
        with_disabled_apps,
    ):
        user = SimpleNamespace(refresh_from_db=Mock())
        backend = SimpleNamespace(name="twitter")
        response = {"profile_image_url": "http://example.com/profile_images/1/abc_bigger.jpg"}

        with patch(
            "baseapp_social_auth.tests.pipeline.requests.get",
            return_value=SimpleNamespace(content=b"image-bytes"),
        ) as mock_get:
            set_avatar(is_new=True, backend=backend, user=user, response=response)

        user.refresh_from_db.assert_called_once()
        mock_get.assert_called_once_with(
            "http://example.com/profile_images/1/abc_400x400.jpg",
            params={},
        )

    def test_set_avatar_skips_default_twitter_profile_images_without_profiles(
        self,
        with_disabled_apps,
    ):
        user = SimpleNamespace(refresh_from_db=Mock())
        backend = SimpleNamespace(name="twitter")
        response = {
            "profile_image_url": (
                "http://example.com/sticky/default_profile_images/default_profile_3_bigger.png"
            )
        }

        with patch("baseapp_social_auth.tests.pipeline.requests.get") as mock_get:
            set_avatar(is_new=True, backend=backend, user=user, response=response)

        user.refresh_from_db.assert_not_called()
        mock_get.assert_not_called()
