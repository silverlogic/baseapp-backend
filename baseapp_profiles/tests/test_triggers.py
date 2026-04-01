import pytest
import swapper
from django.contrib.auth import get_user_model

from baseapp_core.tests.factories import UserFactory

pytestmark = pytest.mark.django_db(transaction=True)

User = get_user_model()
Profile = swapper.load_model("baseapp_profiles", "Profile")


# ---------------------------------------------------------------------------
# INSERT trigger: automatic profile creation
# ---------------------------------------------------------------------------


def test_user_creation_creates_profile():
    user = UserFactory(first_name="John", last_name="Doe")
    user.refresh_from_db()
    assert user.profile_id is not None


def test_user_creation_sets_profile_name():
    user = UserFactory(first_name="John", last_name="Doe")
    user.refresh_from_db()
    assert user.profile.name == "John Doe"


def test_user_creation_profile_name_is_trimmed():
    # Leading/trailing whitespace on the outer edges of the concatenated name is removed.
    # e.g. empty first_name produces " Doe" which becomes "Doe" after TRIM.
    user = UserFactory(first_name="", last_name="Doe")
    user.refresh_from_db()
    assert user.profile.name == "Doe"


def test_user_creation_sets_profile_owner():
    user = UserFactory(first_name="John", last_name="Doe")
    user.refresh_from_db()
    assert user.profile.owner_id == user.pk


def test_user_creation_sets_profile_target():
    user = UserFactory(first_name="John", last_name="Doe")
    user.refresh_from_db()
    profile = user.profile
    assert profile.target_object_id == user.pk


def test_user_creation_with_existing_profile_does_not_duplicate():
    user = UserFactory(first_name="John", last_name="Doe")
    user.refresh_from_db()
    profile_id = user.profile_id
    profile_count = Profile.objects.filter(owner=user).count()
    assert profile_count == 1
    assert profile_id is not None


# ---------------------------------------------------------------------------
# UPDATE trigger: profile name kept in sync
# ---------------------------------------------------------------------------


def test_user_first_name_update_syncs_profile_name():
    user = UserFactory(first_name="John", last_name="Doe")
    user.refresh_from_db()

    user.first_name = "Jane"
    user.save()

    user.profile.refresh_from_db()
    assert user.profile.name == "Jane Doe"


def test_user_last_name_update_syncs_profile_name():
    user = UserFactory(first_name="John", last_name="Doe")
    user.refresh_from_db()

    user.last_name = "Smith"
    user.save()

    user.profile.refresh_from_db()
    assert user.profile.name == "John Smith"


def test_user_update_profile_name_is_trimmed():
    # Setting last_name to empty string leaves "John " which TRIM reduces to "John".
    user = UserFactory(first_name="John", last_name="Doe")
    user.refresh_from_db()

    user.last_name = ""
    user.save()

    user.profile.refresh_from_db()
    assert user.profile.name == "John"


def test_unrelated_user_update_does_not_affect_other_profile():
    user1 = UserFactory(first_name="Alice", last_name="A")
    user2 = UserFactory(first_name="Bob", last_name="B")
    user1.refresh_from_db()
    user2.refresh_from_db()

    user1.first_name = "Alicia"
    user1.save()

    user2.profile.refresh_from_db()
    assert user2.profile.name == "Bob B"
