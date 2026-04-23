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


def test_user_creation_reuses_existing_profile_on_conflict():
    """
    When a Profile with the same (target_content_type, target_object_id) already
    exists before the User is inserted, the trigger's ON CONFLICT … DO UPDATE branch
    should be taken: no second profile is created and the user is linked to the
    pre-existing profile.
    """
    from django.contrib.contenttypes.models import ContentType
    from django.db import connection

    # Advance the sequence so we know the PK the next INSERT will receive.
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT nextval(pg_get_serial_sequence(%s, 'id'))",
            [User._meta.db_table],
        )
        next_user_id = cursor.fetchone()[0]

    # Seed a Profile that shares the same unique key the trigger would insert.
    # owner_id has db_constraint=False so pointing at a not-yet-existing user is safe.
    user_ct = ContentType.objects.get_for_model(User)
    existing_profile = Profile.objects.create(
        owner_id=next_user_id,
        target_content_type=user_ct,
        target_object_id=next_user_id,
        name="Pre-existing",
        status=Profile.ProfileStatus.PUBLIC,
    )

    # Create the user with the reserved PK – trigger hits ON CONFLICT and the
    # DO UPDATE branch refreshes owner_id, name, and modified on the existing profile.
    user = UserFactory(id=next_user_id, first_name="John", last_name="Doe")
    user.refresh_from_db()

    assert Profile.objects.filter(owner_id=next_user_id).count() == 1
    assert user.profile_id == existing_profile.pk

    existing_profile.refresh_from_db()
    assert existing_profile.owner_id == next_user_id
    assert existing_profile.name == "John Doe"


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
