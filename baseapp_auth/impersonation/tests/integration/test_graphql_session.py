import pytest
from django.test import override_settings
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework_simplejwt.utils import datetime_to_epoch

from baseapp_auth.tests.factories import UserFactory
from baseapp_core.graphql.testing.fixtures import graphql_query

from ...models import ImpersonationSession
from ...signals import impersonation_denied, impersonation_ended, impersonation_started
from ..fixtures import bearer

pytestmark = pytest.mark.django_db

START = """
    mutation ImpersonationStart($input: ImpersonationStartInput!) {
        impersonationStart(input: $input) {
            access
            refresh
            session { id expiresAt readOnly isActive target { id fullName } }
        }
    }
"""

END = """
    mutation ImpersonationEnd($input: ImpersonationEndInput!) {
        impersonationEnd(input: $input) {
            session { id isActive endReason endedAt }
        }
    }
"""

ME = """
    query {
        me {
            id
            impersonation {
                id
                startedAt
                expiresAt
                readOnly
                impersonator { id fullName }
            }
        }
    }
"""


def start(django_client, impersonator, target, reason: str = "Support ticket 42") -> dict:
    django_client.force_login(impersonator)
    return graphql_query(
        START,
        input_data={"targetUser": target.relay_id, "reason": reason},
        client=django_client,
    ).json()


def test_superuser_starts_a_session(django_client, superuser, member) -> None:
    received = []
    impersonation_started.connect(lambda **kw: received.append(kw), weak=False, dispatch_uid="t1")
    try:
        content = start(django_client, superuser, member)
    finally:
        impersonation_started.disconnect(dispatch_uid="t1")

    assert "errors" not in content
    payload = content["data"]["impersonationStart"]
    assert payload["session"]["target"]["id"] == member.relay_id
    assert payload["session"]["readOnly"] is True
    assert payload["session"]["isActive"] is True

    session = ImpersonationSession.objects.get()
    assert session.impersonator == superuser
    assert session.target == member
    assert session.reason == "Support ticket 42"
    assert received[0]["session"] == session

    access = AccessToken(payload["access"])
    refresh = RefreshToken(payload["refresh"])
    for token in (access, refresh):
        assert str(token["user_id"]) == str(member.pk)
        assert token["imp"] == superuser.pk
        assert token["imp_sid"] == session.pk
        assert token["exp"] <= datetime_to_epoch(session.expires_at)
    assert refresh["exp"] == datetime_to_epoch(session.expires_at)


@override_settings(BASEAPP_AUTH_IMPERSONATION_TTL=120)
def test_session_length_follows_ttl(django_client, superuser, member) -> None:
    start(django_client, superuser, member)
    session = ImpersonationSession.objects.get()
    assert (session.expires_at - session.started_at).total_seconds() == 120


@override_settings(BASEAPP_AUTH_IMPERSONATION_READ_ONLY=False)
def test_act_as_session_is_not_read_only(django_client, superuser, member) -> None:
    content = start(django_client, superuser, member)
    assert content["data"]["impersonationStart"]["session"]["readOnly"] is False


@pytest.mark.parametrize(
    "target_kwargs",
    [{"is_superuser": True}, {"is_active": False}],
    ids=["superuser", "inactive"],
)
def test_default_rules_refuse_some_targets(django_client, superuser, target_kwargs) -> None:
    target = UserFactory(**target_kwargs)
    content = start(django_client, superuser, target)
    assert content["errors"][0]["extensions"]["code"] == "permission_required"
    assert not ImpersonationSession.objects.exists()


def test_cannot_impersonate_self(django_client, superuser) -> None:
    content = start(django_client, superuser, superuser)
    assert content["errors"][0]["extensions"]["code"] == "permission_required"


def test_non_superuser_is_refused_and_denied_signal_fires(django_client, member) -> None:
    received = []
    impersonation_denied.connect(lambda **kw: received.append(kw), weak=False, dispatch_uid="t2")
    other = UserFactory()
    try:
        content = start(django_client, member, other)
    finally:
        impersonation_denied.disconnect(dispatch_uid="t2")

    assert content["errors"][0]["extensions"]["code"] == "permission_required"
    assert received[0]["impersonator"] == member
    assert received[0]["target"] == other


def allow_staff(impersonator, target, request) -> bool:
    return impersonator.is_staff and request is not None


@override_settings(
    BASEAPP_AUTH_IMPERSONATION_CAN_IMPERSONATE=(
        "baseapp_auth.impersonation.tests.integration.test_graphql_session.allow_staff"
    )
)
def test_project_hook_decides(django_client, member) -> None:
    staff = UserFactory(is_staff=True)
    content = start(django_client, staff, member)
    assert "errors" not in content


def test_reason_is_required(django_client, superuser, member) -> None:
    content = start(django_client, superuser, member, reason="   ")
    assert content["errors"][0]["extensions"]["code"] == "invalid_input"
    assert not ImpersonationSession.objects.exists()


def test_target_must_be_a_user(django_client, superuser) -> None:
    django_client.force_login(superuser)
    content = graphql_query(
        START,
        input_data={"targetUser": "VXNlcjo5OTk5OTk=", "reason": "x"},
        client=django_client,
    ).json()
    assert content["errors"][0]["extensions"]["code"] == "not_found"


def test_anonymous_cannot_start(graphql_client, member) -> None:
    content = graphql_client(
        START, input_data={"targetUser": member.relay_id, "reason": "x"}
    ).json()
    assert content["errors"][0]["extensions"]["code"] == "authentication_required"


def test_me_shows_the_session(django_client, superuser, member, start_session) -> None:
    session, tokens = start_session()

    content = graphql_query(ME, client=django_client, headers=bearer(tokens["access"])).json()

    assert "errors" not in content
    assert content["data"]["me"]["id"] == member.relay_id
    impersonation = content["data"]["me"]["impersonation"]
    assert impersonation["impersonator"]["id"] == superuser.relay_id
    assert impersonation["readOnly"] is True
    assert impersonation["id"] == session.relay_id


def test_me_has_no_session_on_an_ordinary_login(django_client, member) -> None:
    access = str(RefreshToken.for_user(member).access_token)
    content = graphql_query(ME, client=django_client, headers=bearer(access)).json()
    assert content["data"]["me"]["id"] == member.relay_id
    assert content["data"]["me"]["impersonation"] is None


def test_no_nested_sessions(django_client, start_session) -> None:
    _session, tokens = start_session()
    other = UserFactory()
    content = graphql_query(
        START,
        input_data={"targetUser": other.relay_id, "reason": "x"},
        client=django_client,
        headers=bearer(tokens["access"]),
    ).json()
    # Read-only sessions refuse the mutation outright; act-as ones refuse it inside.
    assert content["errors"][0]["extensions"]["code"] in (
        "impersonation_read_only",
        "impersonation_active",
    )


@override_settings(BASEAPP_AUTH_IMPERSONATION_READ_ONLY=False)
def test_no_nested_sessions_when_acting_as(django_client, start_session) -> None:
    _session, tokens = start_session()
    content = graphql_query(
        START,
        input_data={"targetUser": UserFactory().relay_id, "reason": "x"},
        client=django_client,
        headers=bearer(tokens["access"]),
    ).json()
    assert content["errors"][0]["extensions"]["code"] == "impersonation_active"


def test_end_from_inside_the_session(django_client, start_session) -> None:
    session, tokens = start_session()
    received = []
    impersonation_ended.connect(lambda **kw: received.append(kw), weak=False, dispatch_uid="t3")
    try:
        content = graphql_query(
            END,
            variables={"input": {}},
            client=django_client,
            headers=bearer(tokens["access"]),
        ).json()
    finally:
        impersonation_ended.disconnect(dispatch_uid="t3")

    assert "errors" not in content
    payload = content["data"]["impersonationEnd"]["session"]
    assert payload["isActive"] is False
    assert payload["endReason"] == "ENDED"
    session.refresh_from_db()
    assert session.ended_at is not None
    assert session.end_reason == ImpersonationSession.EndReason.ENDED
    assert received[0]["reason"] == ImpersonationSession.EndReason.ENDED
    assert not session.actions.exists()

    # The session's tokens stop working at once.
    response = graphql_query(ME, client=django_client, headers=bearer(tokens["access"]))
    assert response.status_code == 401
    assert response.json()["code"] == "impersonation_ended"


def test_impersonator_ends_from_own_account(django_client, superuser, start_session) -> None:
    session, _tokens = start_session()
    django_client.force_login(superuser)
    content = graphql_query(
        END, input_data={"session": session.relay_id}, client=django_client
    ).json()
    assert content["data"]["impersonationEnd"]["session"]["isActive"] is False


def test_others_cannot_end_a_session(django_client, member, start_session) -> None:
    session, _tokens = start_session()
    django_client.force_login(UserFactory())
    content = graphql_query(
        END, input_data={"session": session.relay_id}, client=django_client
    ).json()
    assert content["errors"][0]["extensions"]["code"] == "permission_required"


def test_staff_with_permission_revokes(django_client, start_session) -> None:
    from django.contrib.auth.models import Permission

    session, _tokens = start_session()
    staff = UserFactory()
    staff.user_permissions.add(Permission.objects.get(codename="change_impersonationsession"))
    django_client.force_login(staff)
    graphql_query(END, input_data={"session": session.relay_id}, client=django_client)
    session.refresh_from_db()
    assert session.end_reason == ImpersonationSession.EndReason.REVOKED


def test_end_without_a_session(django_client, superuser) -> None:
    django_client.force_login(superuser)
    content = graphql_query(END, variables={"input": {}}, client=django_client).json()
    assert content["errors"][0]["extensions"]["code"] == "not_found"


def test_session_node_visibility(django_client, superuser, start_session) -> None:
    session, _tokens = start_session()
    query = "query($id: ID!) { node(id: $id) { ... on ImpersonationSession { id reason } } }"

    django_client.force_login(superuser)
    content = graphql_query(query, variables={"id": session.relay_id}, client=django_client)
    assert content.json()["data"]["node"]["reason"] == "Support ticket 42"

    django_client.force_login(UserFactory())
    content = graphql_query(query, variables={"id": session.relay_id}, client=django_client)
    assert content.json()["data"]["node"] is None
