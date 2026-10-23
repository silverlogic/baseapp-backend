import pytest
from django.test import override_settings

from baseapp_core.graphql.testing.fixtures import graphql_query

from ...models import ImpersonationAction
from ...signals import impersonation_action
from ..fixtures import bearer

pytestmark = pytest.mark.django_db

# Any mutation will do: in a read-only session it is refused before it resolves, and in an
# act-as session it is recorded before it resolves.
DELETE_NODE = """
    mutation DeleteSomething($input: DeleteNodeInput!) {
        deleteNode(input: $input) { deletedID }
    }
"""


PHONE = "+14155552671"


def users_url(user) -> str:
    return f"/v1/users/{user.pk}"


class TestReadOnly:
    def test_rest_reads_work(self, client, member, start_session) -> None:
        _session, tokens = start_session()
        response = client.get("/v1/users/me", **bearer(tokens["access"]))
        assert response.status_code == 200
        assert response.json()["email"] == member.email

    def test_rest_writes_are_refused(self, client, member, start_session) -> None:
        session, tokens = start_session()
        response = client.patch(
            users_url(member), {"phone_number": PHONE}, **bearer(tokens["access"])
        )
        assert response.status_code == 403
        assert response.json()["code"] == "impersonation_read_only"
        member.refresh_from_db()
        assert str(member.phone_number) != PHONE
        assert not session.actions.exists()

    @override_settings(BASEAPP_AUTH_IMPERSONATION_READ_ONLY_ALLOWLIST=[r"^/v1/users/\d+$"])
    def test_allowlisted_rest_write_runs_and_is_recorded(
        self, client, member, start_session
    ) -> None:
        session, tokens = start_session()
        response = client.patch(
            users_url(member), {"phone_number": PHONE}, **bearer(tokens["access"])
        )
        assert response.status_code == 200
        action = session.actions.get()
        assert (action.method, action.path, action.status_code) == (
            "PATCH",
            users_url(member),
            200,
        )

    def test_graphql_queries_work(self, django_client, member, start_session) -> None:
        _session, tokens = start_session()
        content = graphql_query(
            "query { me { id } }", client=django_client, headers=bearer(tokens["access"])
        ).json()
        assert content["data"]["me"]["id"] == member.relay_id

    def test_graphql_mutations_are_refused(self, django_client, start_session) -> None:
        session, tokens = start_session()
        content = graphql_query(
            DELETE_NODE,
            input_data={"id": "x"},
            client=django_client,
            headers=bearer(tokens["access"]),
        ).json()
        assert content["errors"][0]["extensions"]["code"] == "impersonation_read_only"
        assert not session.actions.exists()

    @override_settings(BASEAPP_AUTH_IMPERSONATION_READ_ONLY_ALLOWLIST=["deleteNode"])
    def test_allowlisted_mutation_runs_and_is_recorded(self, django_client, start_session) -> None:
        session, tokens = start_session()
        content = graphql_query(
            DELETE_NODE,
            input_data={"id": "x"},
            client=django_client,
            headers=bearer(tokens["access"]),
        ).json()
        assert content["errors"][0].get("extensions", {}).get("code") != "impersonation_read_only"
        action = session.actions.get()
        assert action.operation_name == "deleteNode"
        assert action.method == "POST"
        assert action.path == "/graphql"
        assert action.status_code is None


class TestActAs:
    @pytest.fixture(autouse=True)
    def act_as(self, settings) -> None:
        settings.BASEAPP_AUTH_IMPERSONATION_READ_ONLY = False

    def test_rest_writes_run_and_are_recorded(self, client, member, start_session) -> None:
        session, tokens = start_session()
        received = []
        impersonation_action.connect(
            lambda **kw: received.append(kw), weak=False, dispatch_uid="act-as-rest"
        )
        try:
            response = client.patch(
                users_url(member), {"phone_number": PHONE}, **bearer(tokens["access"])
            )
        finally:
            impersonation_action.disconnect(dispatch_uid="act-as-rest")

        assert response.status_code == 200
        member.refresh_from_db()
        assert str(member.phone_number) == PHONE
        action = session.actions.get()
        assert action.method == "PATCH"
        assert action.status_code == 200
        assert received[0]["action"] == action
        assert received[0]["session"] == session

    def test_failed_rest_writes_are_recorded_with_their_status(self, client, start_session) -> None:
        session, tokens = start_session()
        response = client.patch("/v1/users/0", {"phone_number": PHONE}, **bearer(tokens["access"]))
        assert response.status_code == 404
        assert session.actions.get().status_code == 404

    def test_reads_are_not_recorded(self, client, start_session) -> None:
        session, tokens = start_session()
        client.get("/v1/users/me", **bearer(tokens["access"]))
        assert not session.actions.exists()

    def test_graphql_mutations_run_and_are_recorded(self, django_client, start_session) -> None:
        session, tokens = start_session()
        content = graphql_query(
            DELETE_NODE,
            input_data={"id": "x"},
            client=django_client,
            headers=bearer(tokens["access"]),
        ).json()
        # The mutation itself fails (no such node), but it ran as the target.
        assert content["errors"][0].get("extensions", {}).get("code") != "impersonation_read_only"
        action = session.actions.get()
        assert action.operation_name == "deleteNode"

    def test_account_security_writes_are_never_allowed(self, client, start_session) -> None:
        session, tokens = start_session()
        response = client.post(
            "/v1/users/change-password",
            {"current_password": "x", "new_password": "y", "confirm_new_password": "y"},
            **bearer(tokens["access"]),
        )
        assert response.status_code == 403
        assert response.json()["code"] == "impersonation_forbidden"
        assert not session.actions.exists()

    def test_denylisted_mutations_are_refused(self, django_client, settings, start_session) -> None:
        settings.BASEAPP_AUTH_IMPERSONATION_DENYLIST = ["deleteNode"]
        session, tokens = start_session()
        content = graphql_query(
            DELETE_NODE,
            input_data={"id": "x"},
            client=django_client,
            headers=bearer(tokens["access"]),
        ).json()
        assert content["errors"][0]["extensions"]["code"] == "impersonation_forbidden"
        assert not session.actions.exists()

    def test_graphql_queries_are_not_recorded(self, django_client, start_session) -> None:
        session, tokens = start_session()
        graphql_query("query { me { id } }", client=django_client, headers=bearer(tokens["access"]))
        assert not session.actions.exists()


def test_ordinary_requests_are_untouched(client, member) -> None:
    client.force_authenticate(member)
    response = client.patch(users_url(member), {"phone_number": PHONE})
    assert response.status_code == 200
    assert not ImpersonationAction.objects.exists()
