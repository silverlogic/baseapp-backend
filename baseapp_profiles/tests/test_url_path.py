import unicodedata

import pytest
import swapper

from baseapp_core.tests.factories import UserFactory
from baseapp_pages.tests.factories import URLPathFactory

pytestmark = pytest.mark.django_db

Profile = swapper.load_model("baseapp_profiles", "Profile")


def test_profile_generate_url_path_with_valid_name() -> None:
    user = UserFactory(first_name="Jonathan", last_name="Doe")
    profile = Profile.objects.get(owner=user)
    assert profile.url_path.path == "/JonathanDoe"


def test_profile_generate_url_path_with_short_name() -> None:
    user = UserFactory(first_name="Joe", last_name="Doe")
    profile = Profile.objects.get(owner=user)
    # "JoeDoe" is 6 chars, so it gets padded with random digits to a min length of 8.
    assert profile.url_path.path.startswith("/JoeDoe")
    assert len(profile.url_path.path) == 9
    assert profile.url_path.path[-1].isdigit()


def test_profile_generate_url_path_with_existing_path() -> None:
    URLPathFactory(path="/JanetDoe", is_active=True, language=None)
    user = UserFactory(first_name="Janet", last_name="Doe")
    profile = Profile.objects.get(owner=user)
    assert profile.url_path.path == "/JanetDoe1"


def test_profile_generate_url_path_strips_accents_to_ascii() -> None:
    # Names with accents must not leak the accented char into the URL path (an accented
    # path previously 404'd once percent-encoded). Capitalization is preserved; only the
    # accent is folded to ASCII.
    user = UserFactory(first_name="Foobar", last_name="Báz")
    profile = Profile.objects.get(owner=user)
    assert profile.url_path.path == "/FoobarBaz"
    assert profile.url_path.path.isascii()


def test_profile_generate_url_path_normalizes_decomposed_unicode() -> None:
    # A provider may send the name decomposed (NFD: "a" + combining acute) instead of
    # NFC. The ASCII fold normalizes either form down to the same handle.
    decomposed_last = unicodedata.normalize("NFD", "Báz")
    assert decomposed_last != "Báz"  # sanity: it really is decomposed
    user = UserFactory(first_name="Foobar", last_name=decomposed_last)
    profile = Profile.objects.get(owner=user)
    assert profile.url_path.path == "/FoobarBaz"
    assert profile.url_path.path.isascii()


def test_profile_generate_url_path_with_mixed_unicode_name() -> None:
    user = UserFactory(first_name="Bäz", last_name="Qüxson")
    profile = Profile.objects.get(owner=user)
    assert profile.url_path.path == "/BazQuxson"
    assert profile.url_path.path.isascii()


def test_profile_generate_url_path_drops_non_decomposable_latin_letters() -> None:
    # Documented (lossy) behavior: Latin letters with no NFKD decomposition to ASCII —
    # e.g. ß, ø, ł, đ, æ — are DROPPED rather than transliterated (so "ß" does not become
    # "ss"). Pinned here so that changing the folding (e.g. adding transliteration) is a
    # deliberate decision rather than a silent regression.
    user = UserFactory(first_name="Foo", last_name="Straße")
    profile = Profile.objects.get(owner=user)
    assert profile.url_path.path == "/FooStrae"  # the "ß" is dropped, not turned into "ss"
    assert profile.url_path.path.isascii()


def test_profile_generate_url_path_with_name_and_emoji() -> None:
    # A name with a usable part plus an emoji keeps the usable part and drops the emoji
    # (never leaking it into the URL), without falling back to the email.
    # "JonDoe" is 6 chars, so it is padded to the 8-char minimum with random digits.
    user = UserFactory(first_name="Jon", last_name="Doe 😀", email="jon@example.com")
    profile = Profile.objects.get(owner=user)
    assert profile.url_path.path.startswith("/JonDoe")
    assert len(profile.url_path.path) == 9
    assert profile.url_path.path[-1].isdigit()
    assert profile.url_path.path.isascii()


def test_profile_generate_url_path_falls_back_to_email_when_name_has_no_ascii() -> None:
    # An emoji-only (or fully non-latin) name produces an empty handle, so it falls back
    # to the local-part of the owner's email instead of a string of random digits.
    user = UserFactory(first_name="😀", last_name="", email="coolperson@example.com")
    profile = Profile.objects.get(owner=user)
    assert profile.url_path.path == "/coolperson"
    assert profile.url_path.path.isascii()


def test_profile_generate_url_path_last_resort_random_digits() -> None:
    # No usable name and no owner email -> the handle falls all the way through to a
    # string of random digits so it is still non-empty.
    profile = Profile(name="😀")  # unsaved, no owner
    path = profile.generate_url_path()
    assert path.startswith("/")
    assert len(path) == 9
    assert path[1:].isdigit()


def test_profile_generate_url_path_assigns_unique_paths_for_duplicate_names() -> None:
    # Two users with the exact same name must not collide: the second profile gets a
    # numeric suffix so each url_path stays unique (URLPath.path is unique at the DB level).
    user_1 = UserFactory(first_name="Jonathan", last_name="Doe")
    user_2 = UserFactory(first_name="Jonathan", last_name="Doe")
    profile_1 = Profile.objects.get(owner=user_1)
    profile_2 = Profile.objects.get(owner=user_2)
    assert profile_1.url_path.path == "/JonathanDoe"
    assert profile_2.url_path.path == "/JonathanDoe1"
    assert profile_1.url_path.path != profile_2.url_path.path
