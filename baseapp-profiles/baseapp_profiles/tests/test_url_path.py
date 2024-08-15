import pytest
import swapper
from baseapp_pages.tests.factories import URLPathFactory

from .factories import ProfileFactory

pytest.skip("auto generated url_path disabled", allow_module_level=True)

pytestmark = pytest.mark.django_db

Profile = swapper.load_model("baseapp_profiles", "Profile")


def test_profile_generate_url_path():
    profile = ProfileFactory()
    assert profile.url_path.path == f"profile/{profile.pk}"


def test_profile_generate_url_path_random():
    last_profile = ProfileFactory()
    next_profile_id = (
        int(last_profile.pk) + 2
    )  # TODO: there is an issue with the factories thats causing duplicated profiles to be created because of profile.owner subfactory
    URLPathFactory(path=f"profile/{next_profile_id}", is_active=True, language=None)
    profile = ProfileFactory()
    assert len(profile.url_path.path) == 44
