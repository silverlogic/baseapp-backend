"""Graphene vs Strawberry parity for the blocks slice of the schema.

Each test sends the same document to `/graphql` (Graphene) and `/graphql/strawberry` and asserts
identical responses, then asserts Strawberry needs no more SQL queries than Graphene and stays flat
when the data grows.
"""

import pytest
import swapper
from django.test import override_settings
from graphql_relay import to_global_id
from rest_framework.authtoken.models import Token

from baseapp_core.strawberry.parity import compare_schemas
from baseapp_core.strawberry.testing import (
    GRAPHENE_GRAPHQL_URL,
    STRAWBERRY_GRAPHQL_URL,
    run_on_both,
    run_on_endpoint,
)
from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.tests.factories import ProfileFactory

from .factories import BlockFactory
from .test_graphql_mutations import BLOCK_TOGGLE_GRAPHQL
from .test_graphql_queries_object_blocks import (
    COUNTS_ONLY_QUERY,
    PROFILE_BLOCKING_LIST_QUERY,
)

Block = swapper.load_model("baseapp_blocks", "Block")

pytestmark = pytest.mark.django_db

BLOCK_NODE_QUERY = """
    query BlockNode($id: ID!) {
        node(id: $id) {
            __typename
            id
            ... on Block {
                actor { id name }
                target { id name }
            }
        }
    }
"""

COUNTED_CONNECTION_QUERY = """
    query Blockers($id: ID!) {
        node(id: $id) {
            ... on BlocksInterface {
                blockers(first: 2) {
                    totalCount
                    edgeCount
                    pageInfo { hasNextPage hasPreviousPage startCursor endCursor }
                    edges { cursor node { id actor { id } } }
                }
            }
        }
    }
"""

BLOCK_TOGGLE_WITH_CLIENT_ID = BLOCK_TOGGLE_GRAPHQL.replace(
    "blockToggle(input: $input) {",
    "blockToggle(input: $input) {\n    clientMutationId\n    errors { field messages }\n    blockDeletedId",
)

# Differences accepted on purpose. Anything else in the ported types fails the test.
ACCEPTED_SCHEMA_DIFFS = {
    # Strawberry interfaces that inherit Node declare it; additive, harmless for clients.
    ("BlocksInterface", "interfaces"),
    # Graphene's DjangoConnectionField `offset` arg; no frontend operation uses it.
    ("BlocksInterface.blockers(offset)", "argument"),
    ("BlocksInterface.blocking(offset)", "argument"),
    ("Profile.blockers(offset)", "argument"),
    ("Profile.blocking(offset)", "argument"),
}
# Only partially ported in the POC: these types' remaining fields still live in Graphene alone.
PARTIAL_TYPES = {"Profile", "Query", "Mutation"}
NOT_YET_PORTED = {
    ("Profile", "interfaces"),
    ("Block.user", "missing field"),  # needs the User type
    ("BlockTogglePayload._debug", "missing field"),  # DjangoDebug has no Strawberry equivalent
}


def _is_accepted(diff) -> bool:
    key = (diff.path, diff.kind)
    if key in ACCEPTED_SCHEMA_DIFFS or key in NOT_YET_PORTED:
        return True
    return diff.kind == "missing field" and diff.path.split(".")[0] in PARTIAL_TYPES


def _make_superuser(client) -> None:
    client.user.is_superuser = True
    client.user.save()


def _assert_same_data(result) -> None:
    assert "errors" not in result.graphene.content, result.graphene.content
    assert result.strawberry.content == result.graphene.content


def _assert_not_more_queries(result, label: str) -> None:
    print(result.report(label))
    assert result.strawberry.queries.count <= result.graphene.queries.count, (
        f"{result.report(label)}\nGRAPHENE:{result.graphene.queries.log}"
        f"\nSTRAWBERRY:{result.strawberry.queries.log}"
    )


def test_schema_parity_for_ported_types() -> None:
    from testproject.graphql import schema as graphene_schema
    from testproject.strawberry_schema import schema as strawberry_schema

    diffs = compare_schemas(graphene_schema.graphql_schema, strawberry_schema._schema)
    unexpected = [str(d) for d in diffs if not _is_accepted(d)]
    assert unexpected == [], "\n".join(unexpected)


@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
@pytest.mark.parametrize("volume", [3, 20])
def test_counts_on_node_match_and_stay_flat(django_user_client, volume) -> None:
    _make_superuser(django_user_client)
    target = ProfileFactory()
    for _ in range(volume):
        actor = ProfileFactory(owner=UserFactory())
        BlockFactory(actor=actor, target=target, user=actor.owner)

    result = run_on_both(django_user_client, COUNTS_ONLY_QUERY, {"id": target.relay_id})

    _assert_same_data(result)
    assert result.strawberry.content["data"]["node"]["blockersCount"] == volume
    _assert_not_more_queries(result, f"counts-on-node volume={volume}")


@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
def test_counts_perm_denied_match(django_user_client) -> None:
    target = ProfileFactory()
    for _ in range(3):
        actor = ProfileFactory(owner=UserFactory())
        BlockFactory(actor=actor, target=target, user=actor.owner)

    result = run_on_both(django_user_client, COUNTS_ONLY_QUERY, {"id": target.relay_id})

    _assert_same_data(result)
    assert result.strawberry.content["data"]["node"]["blockersCount"] is None
    _assert_not_more_queries(result, "counts-perm-denied")


@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
def test_nested_list_is_flat_and_not_worse(django_user_client) -> None:
    """`blocking.edges.node.target.blockersCount`: the annotation must reach the nested Profile."""
    _make_superuser(django_user_client)
    actor = ProfileFactory(owner=django_user_client.user)
    counts = {}
    for volume in (3, 20):
        while Block.objects.filter(actor=actor).count() < volume:
            BlockFactory(
                actor=actor,
                target=ProfileFactory(owner=UserFactory()),
                user=django_user_client.user,
            )
        result = run_on_both(
            django_user_client, PROFILE_BLOCKING_LIST_QUERY, {"id": actor.relay_id}
        )

        def edges(content: dict) -> list[dict]:
            return sorted(
                content["data"]["node"]["blocking"]["edges"], key=lambda e: e["node"]["id"]
            )

        assert "errors" not in result.strawberry.content, result.strawberry.content
        assert edges(result.strawberry.content) == edges(result.graphene.content)
        assert len(edges(result.strawberry.content)) == volume
        _assert_not_more_queries(result, f"nested-list volume={volume}")
        counts[volume] = result.strawberry.queries.count

    assert counts[3] == counts[20], f"Strawberry N+1: {counts}"


@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
def test_counted_connection_shape_matches(django_user_client) -> None:
    _make_superuser(django_user_client)
    target = ProfileFactory()
    blocks = []
    for _ in range(3):
        actor = ProfileFactory(owner=UserFactory())
        blocks.append(BlockFactory(actor=actor, target=target, user=actor.owner))

    result = run_on_both(django_user_client, COUNTED_CONNECTION_QUERY, {"id": target.relay_id})

    assert "errors" not in result.strawberry.content, result.strawberry.content
    graphene_conn = result.graphene.content["data"]["node"]["blockers"]
    strawberry_conn = result.strawberry.content["data"]["node"]["blockers"]
    assert strawberry_conn["totalCount"] == graphene_conn["totalCount"] == 3
    assert strawberry_conn["edgeCount"] == graphene_conn["edgeCount"] == 2
    assert strawberry_conn["pageInfo"] == graphene_conn["pageInfo"]
    assert [e["cursor"] for e in strawberry_conn["edges"]] == [
        e["cursor"] for e in graphene_conn["edges"]
    ]
    _assert_not_more_queries(result, "counted-connection")


@pytest.mark.parametrize("public_ids", [True, False])
def test_block_node_ids_and_get_node_permission(django_user_client, public_ids) -> None:
    with override_settings(ENABLE_PUBLIC_ID_LOGIC=public_ids):
        block = BlockFactory(actor=ProfileFactory(), target=ProfileFactory())
        block_id = block.relay_id
        if not public_ids:
            assert block_id == to_global_id("Block", block.pk)

        denied = run_on_both(django_user_client, BLOCK_NODE_QUERY, {"id": block_id})
        _assert_same_data(denied)
        assert denied.strawberry.content["data"]["node"] is None

        _make_superuser(django_user_client)
        allowed = run_on_both(django_user_client, BLOCK_NODE_QUERY, {"id": block_id})
        _assert_same_data(allowed)
        assert allowed.strawberry.content["data"]["node"]["id"] == block_id
        assert allowed.strawberry.content["data"]["node"]["actor"]["id"] == block.actor.relay_id
        _assert_not_more_queries(allowed, f"block-node public_ids={public_ids}")


def test_unknown_or_empty_node_id_resolves_to_null(django_user_client) -> None:
    for node_id in ("", to_global_id("Block", 999999)):
        result = run_on_both(django_user_client, BLOCK_NODE_QUERY, {"id": node_id})
        assert result.strawberry.content["data"]["node"] is None


def test_block_toggle_anon_error_matches(client) -> None:
    variables = {
        "input": {
            "actorObjectId": ProfileFactory().relay_id,
            "targetObjectId": ProfileFactory().relay_id,
        }
    }
    result = run_on_both(client, BLOCK_TOGGLE_GRAPHQL, variables)
    graphene_error = result.graphene.content["errors"][0]
    strawberry_error = result.strawberry.content["errors"][0]
    assert strawberry_error["message"] == graphene_error["message"] == "authentication required"
    assert strawberry_error["extensions"]["code"] == "authentication_required"
    assert result.strawberry.content["data"] == result.graphene.content["data"]
    assert Block.objects.count() == 0


def _toggle(client, url: str, actor, target, client_mutation_id: str) -> dict:
    variables = {
        "input": {
            "actorObjectId": actor.relay_id,
            "targetObjectId": target.relay_id,
            "clientMutationId": client_mutation_id,
        }
    }
    return run_on_endpoint(client, url, BLOCK_TOGGLE_WITH_CLIENT_ID, variables).content


def _normalize_toggle(content: dict) -> dict:
    payload = dict(content["data"]["blockToggle"])
    payload["actor"] = {**payload["actor"], "id": "<actor>"}
    payload["target"] = {**payload["target"], "id": "<target>"}
    if payload["block"]:
        payload["block"] = {"node": {"id": "<block>"}}
    if payload["blockDeletedId"]:
        payload["blockDeletedId"] = "<block>"
    return payload


def test_block_toggle_create_and_delete_match(django_user_client) -> None:
    results = {}
    for url in (GRAPHENE_GRAPHQL_URL, STRAWBERRY_GRAPHQL_URL):
        actor = ProfileFactory(owner=django_user_client.user)
        target = ProfileFactory()
        created = _toggle(django_user_client, url, actor, target, "create-1")
        assert "errors" not in created, created
        assert Block.objects.filter(actor=actor, target=target).count() == 1
        deleted = _toggle(django_user_client, url, actor, target, "delete-1")
        assert "errors" not in deleted, deleted
        assert Block.objects.filter(actor=actor, target=target).count() == 0
        results[url] = (created, deleted)

    graphene_created, graphene_deleted = results[GRAPHENE_GRAPHQL_URL]
    strawberry_created, strawberry_deleted = results[STRAWBERRY_GRAPHQL_URL]
    assert strawberry_created["data"]["blockToggle"]["clientMutationId"] == "create-1"
    assert strawberry_created["data"]["blockToggle"]["actor"]["blockingCount"] == 1
    assert _normalize_toggle(strawberry_created) == _normalize_toggle(graphene_created)
    assert _normalize_toggle(strawberry_deleted) == _normalize_toggle(graphene_deleted)


IS_BLOCKED_BY_ME_QUERY = """
    query IsBlocked($id: ID!, $profileId: ID) {
        node(id: $id) {
            ... on BlocksInterface {
                byCurrent: isBlockedByMe
                byArg: isBlockedByMe(profileId: $profileId)
            }
        }
    }
"""


def test_token_auth_and_current_profile_header_match(client) -> None:
    """Anonymous session + `Authorization: Token` and a `Current-Profile` header on both endpoints."""
    user = UserFactory()
    token = Token.objects.create(user=user)
    own_profile = ProfileFactory(owner=user)
    target = ProfileFactory()
    BlockFactory(actor=own_profile, target=target, user=user)
    variables = {"id": target.relay_id, "profileId": own_profile.relay_id}

    anonymous = run_on_both(client, IS_BLOCKED_BY_ME_QUERY, variables)
    _assert_same_data(anonymous)
    assert anonymous.strawberry.content["data"]["node"]["byArg"] is False

    headers = {
        "HTTP_AUTHORIZATION": f"Token {token.key}",
        "HTTP_CURRENT_PROFILE": own_profile.relay_id,
    }
    authenticated = run_on_both(client, IS_BLOCKED_BY_ME_QUERY, variables, headers)
    _assert_same_data(authenticated)
    assert authenticated.strawberry.content["data"]["node"] == {"byCurrent": True, "byArg": True}
    _assert_not_more_queries(authenticated, "token-auth+current-profile")
