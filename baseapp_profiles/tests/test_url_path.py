import string

import pytest
import swapper

from baseapp_core.tests.factories import UserFactory
from baseapp_pages.tests.factories import URLPathFactory

pytestmark = pytest.mark.django_db

Profile = swapper.load_model("baseapp_profiles", "Profile")


def test_profile_generate_url_path_with_valid_name():
    user = UserFactory(first_name="Jonathan", last_name="Doe")
    profile = Profile.objects.get(owner=user)
    username = profile.owner.get_full_name().translate(str.maketrans("", "", string.whitespace))
    assert profile.url_path.path == f"/{username}"


def test_profile_generate_url_path_with_short_name():
    user = UserFactory(first_name="Joe", last_name="Doe")
    profile = Profile.objects.get(owner=user)
    username = profile.owner.get_full_name().translate(str.maketrans("", "", string.whitespace))
    assert username in profile.url_path.path
    assert len(profile.url_path.path) >= 8


def test_profile_generate_url_path_with_existing_path():
    first_name = "Jason"
    last_name = "Sudekis"
    URLPathFactory(path=f"/{first_name}{last_name}", is_active=True, language=None)
    user = UserFactory(first_name=first_name, last_name=last_name)
    profile = Profile.objects.get(owner=user)
    username = profile.owner.get_full_name().translate(str.maketrans("", "", string.whitespace))
    assert profile.url_path.path == f"/{username}1"
