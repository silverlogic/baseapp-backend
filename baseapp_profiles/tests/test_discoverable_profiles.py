import pytest
import swapper

from baseapp_profiles.checks import discoverable_profiles_filter_errors
from baseapp_profiles.discoverability import (
    filter_discoverable_profiles,
    get_discoverable_profiles_filter,
)

from .factories import ProfileFactory

pytestmark = pytest.mark.django_db

Profile = swapper.load_model("baseapp_profiles", "Profile")

HOOK_PATH = "baseapp_profiles.tests.test_discoverable_profiles.hide_hidden_profiles"

ALL_PROFILES = """
    query AllProfiles($q: String) {
        allProfiles(q: $q) {
            edges {
                node {
                    id
                }
            }
        }
    }
"""

PROFILE = """
    query Profile($id: ID!) {
        profile(id: $id) {
            id
        }
    }
"""

NODE = """
    query Node($id: ID!) {
        node(id: $id) {
            id
        }
    }
"""

# Every user (each factory owner and the requesting user) also gets an automatic profile
# with a Faker name, and `q` matches names and URL handles. Search for a token Faker cannot
# produce, so no automatic profile ever matches by chance.
SEARCH_TOKEN = "zqxdana"

seen_users = []


def hide_hidden_profiles(queryset, user):
    seen_users.append(user)
    return queryset.exclude(name__startswith="Hidden")


@pytest.fixture(autouse=True)
def reset_seen_users():
    seen_users.clear()


# Every list query passes `q` explicitly: the shared graphql_query helper reuses its request
# body between calls, so an omitted variable would carry over from an earlier test.
def listed_ids(response) -> list[str]:
    content = response.json()
    assert "errors" not in content, content
    return [edge["node"]["id"] for edge in content["data"]["allProfiles"]["edges"]]


def test_without_filter_lists_every_visible_profile(graphql_user_client) -> None:
    shown = ProfileFactory(name="Shown")
    hidden = ProfileFactory(name="Hidden")

    ids = listed_ids(graphql_user_client(ALL_PROFILES, variables={"q": ""}))

    assert get_discoverable_profiles_filter() is None
    assert shown.relay_id in ids
    assert hidden.relay_id in ids


def test_dotted_path_filter_narrows_the_list(
    settings, django_user_client, graphql_user_client
) -> None:
    settings.BASEAPP_PROFILES_DISCOVERABLE_PROFILES_FILTER = HOOK_PATH
    shown = ProfileFactory(name="Shown")
    hidden = ProfileFactory(name="Hidden")

    ids = listed_ids(graphql_user_client(ALL_PROFILES, variables={"q": ""}))

    assert shown.relay_id in ids
    assert hidden.relay_id not in ids
    assert seen_users == [django_user_client.user]


def test_callable_filter_narrows_the_list(settings, graphql_user_client) -> None:
    settings.BASEAPP_PROFILES_DISCOVERABLE_PROFILES_FILTER = hide_hidden_profiles
    shown = ProfileFactory(name="Shown")
    hidden = ProfileFactory(name="Hidden")

    ids = listed_ids(graphql_user_client(ALL_PROFILES, variables={"q": ""}))

    assert shown.relay_id in ids
    assert hidden.relay_id not in ids


def test_search_applies_on_top_of_the_filter(settings, graphql_user_client) -> None:
    settings.BASEAPP_PROFILES_DISCOVERABLE_PROFILES_FILTER = HOOK_PATH
    match = ProfileFactory(name=f"Shown {SEARCH_TOKEN}")
    other = ProfileFactory(name="Shown Mark")
    hidden_match = ProfileFactory(name=f"Hidden {SEARCH_TOKEN}")

    ids = listed_ids(graphql_user_client(ALL_PROFILES, variables={"q": SEARCH_TOKEN}))

    assert ids == [match.relay_id]
    assert other.relay_id not in ids
    assert hidden_match.relay_id not in ids


def test_filter_cannot_widen_past_profile_visibility(settings, graphql_user_client) -> None:
    # The connection still applies ProfileObjectType.get_queryset after the filter, so a
    # filter that returns everything does not expose other people's private profiles.
    settings.BASEAPP_PROFILES_DISCOVERABLE_PROFILES_FILTER = (
        lambda queryset, user: Profile.objects.all()
    )
    public = ProfileFactory(name="Public", status=Profile.ProfileStatus.PUBLIC)
    private = ProfileFactory(name="Private", status=Profile.ProfileStatus.PRIVATE)

    ids = listed_ids(graphql_user_client(ALL_PROFILES, variables={"q": ""}))

    assert public.relay_id in ids
    assert private.relay_id not in ids


def test_filter_receives_anonymous_user(settings, graphql_client) -> None:
    settings.BASEAPP_PROFILES_DISCOVERABLE_PROFILES_FILTER = HOOK_PATH
    shown = ProfileFactory(name="Shown")
    hidden = ProfileFactory(name="Hidden")

    ids = listed_ids(graphql_client(ALL_PROFILES, variables={"q": ""}))

    assert shown.relay_id in ids
    assert hidden.relay_id not in ids
    assert len(seen_users) == 1
    assert not seen_users[0].is_authenticated


def test_filter_does_not_apply_to_node_lookup(settings, graphql_user_client) -> None:
    settings.BASEAPP_PROFILES_DISCOVERABLE_PROFILES_FILTER = HOOK_PATH
    hidden = ProfileFactory(name="Hidden")

    response = graphql_user_client(PROFILE, variables={"id": hidden.relay_id})

    assert response.json()["data"]["profile"]["id"] == hidden.relay_id
    assert seen_users == []


def test_filter_does_not_apply_to_generic_node_lookup(settings, graphql_user_client) -> None:
    settings.BASEAPP_PROFILES_DISCOVERABLE_PROFILES_FILTER = HOOK_PATH
    hidden = ProfileFactory(name="Hidden")

    response = graphql_user_client(NODE, variables={"id": hidden.relay_id})

    assert response.json()["data"]["node"]["id"] == hidden.relay_id
    assert seen_users == []


def test_filter_discoverable_profiles_helper(settings) -> None:
    shown = ProfileFactory(name="Shown")
    hidden = ProfileFactory(name="Hidden")
    user = shown.owner
    queryset = Profile.objects.filter(pk__in=[shown.pk, hidden.pk])

    assert filter_discoverable_profiles(queryset, user) is queryset

    settings.BASEAPP_PROFILES_DISCOVERABLE_PROFILES_FILTER = HOOK_PATH
    assert list(filter_discoverable_profiles(queryset, user)) == [shown]
    assert seen_users == [user]


def test_system_check_accepts_no_filter_and_valid_filters(settings) -> None:
    assert discoverable_profiles_filter_errors() == []

    settings.BASEAPP_PROFILES_DISCOVERABLE_PROFILES_FILTER = HOOK_PATH
    assert discoverable_profiles_filter_errors() == []

    settings.BASEAPP_PROFILES_DISCOVERABLE_PROFILES_FILTER = hide_hidden_profiles
    assert discoverable_profiles_filter_errors() == []


def test_system_check_reports_a_wrong_dotted_path(settings) -> None:
    settings.BASEAPP_PROFILES_DISCOVERABLE_PROFILES_FILTER = (
        "baseapp_profiles.tests.test_discoverable_profiles.no_such_filter"
    )

    errors = discoverable_profiles_filter_errors()

    assert [error.id for error in errors] == ["baseapp_profiles.E001"]


def test_system_check_reports_a_value_that_is_not_callable(settings) -> None:
    settings.BASEAPP_PROFILES_DISCOVERABLE_PROFILES_FILTER = 42

    errors = discoverable_profiles_filter_errors()

    assert [error.id for error in errors] == ["baseapp_profiles.E002"]
