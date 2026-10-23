import pytest

import baseapp_core.tests.factories as core_factories
import baseapp_message_templates.tests.factories as f
from baseapp_core.graphql.testing.fixtures import graphql_query
from baseapp_core.tests.fixtures import DjangoClient
from baseapp_message_templates.models import EmailTemplate
from baseapp_message_templates.registry import Placeholder, register_email_template
from baseapp_message_templates.tests.fixtures import grant

pytestmark = pytest.mark.django_db

LIST_QUERY = """
query EmailTemplates($group: String, $q: String, $isEditable: Boolean, $isCustomized: Boolean) {
    emailTemplates(group: $group, q: $q, isEditable: $isEditable, isCustomized: $isCustomized) {
        totalCount
        edges {
            node {
                id
                name
                label
                group
                description
                isRegistered
                editableFields
                isCustomized
                previewSubject
                subject
                plainTextContent
                defaultSubject
                defaultPlainText
                placeholders { name help sample }
            }
        }
    }
}
"""

PREVIEW_QUERY = """
query Preview($id: ID!, $subject: String, $plainTextContent: String) {
    node(id: $id) {
        ... on EmailTemplate {
            preview(subject: $subject, plainTextContent: $plainTextContent) {
                subject
                bodyText
                bodyHtml
            }
        }
    }
}
"""

UPDATE_MUTATION = """
mutation Update($input: EmailTemplateUpdateInput!) {
    emailTemplateUpdate(input: $input) {
        emailTemplate { id subject plainTextContent isCustomized previewSubject }
        errors { field messages }
    }
}
"""

SEND_TEST_MUTATION = """
mutation SendTest($input: EmailTemplateSendTestInput!) {
    emailTemplateSendTest(input: $input) {
        sentTo
        errors { field messages }
    }
}
"""


@pytest.fixture
def welcome(email_template_files) -> EmailTemplate:
    register_email_template(
        "tests/welcome",
        label="Welcome email",
        group="accounts",
        description="Sent after sign-up",
        placeholders=[
            Placeholder("user.first_name", help="First name", sample="Ada"),
            Placeholder("site_name", sample="Example"),
        ],
        editable=("subject", "plain_text_content"),
    )
    register_email_template("tests/text-only", label="Code", group="security", editable=())
    f.EmailTemplateFactory(name="tests/text-only")
    return f.EmailTemplateFactory(name="tests/welcome")


def client_for(*codenames: str) -> DjangoClient:
    user = core_factories.UserFactory()
    grant(user, *codenames)
    client = DjangoClient()
    client.force_login(user)
    return client


def run(client, query, **variables) -> dict:
    return graphql_query(query, variables=variables, client=client).json()


def nodes(content) -> list[dict]:
    return [edge["node"] for edge in content["data"]["emailTemplates"]["edges"]]


class TestList:
    def test_hidden_without_view_permission(self, welcome, graphql_user_client) -> None:
        content = graphql_user_client(LIST_QUERY).json()
        assert content["data"]["emailTemplates"]["edges"] == []

        content = graphql_user_client(PREVIEW_QUERY, variables={"id": welcome.relay_id}).json()
        assert content["data"]["node"] is None

    def test_lists_registry_metadata(self, welcome, staff_client) -> None:
        content = run(staff_client, LIST_QUERY)
        assert "errors" not in content
        by_name = {node["name"]: node for node in nodes(content)}
        node = by_name["tests/welcome"]
        assert node["label"] == "Welcome email"
        assert node["group"] == "accounts"
        assert node["description"] == "Sent after sign-up"
        assert node["isRegistered"] is True
        assert node["editableFields"] == ["subject", "plainTextContent"]
        assert node["isCustomized"] is False
        # TC-196: a conditional subject renders with samples instead of showing its source
        assert node["previewSubject"] == "Welcome, Ada to Example"
        assert node["defaultSubject"].startswith("{% if user.first_name %}")
        assert node["defaultPlainText"] == "Hi {{ user.first_name }}, A & B"
        assert node["placeholders"] == [
            {"name": "user.first_name", "help": "First name", "sample": "Ada"},
            {"name": "site_name", "help": "", "sample": "Example"},
        ]
        assert by_name["tests/text-only"]["editableFields"] == []

    def test_unregistered_row(self, email_template_files, staff_client) -> None:
        f.EmailTemplateFactory(name="legacy", subject="Old")
        node = nodes(run(staff_client, LIST_QUERY))[0]
        assert node["label"] == "legacy"
        assert node["isRegistered"] is False
        assert node["editableFields"] == []
        assert node["previewSubject"] is None
        assert node["placeholders"] == []

    def test_filters(self, welcome, staff_client) -> None:
        def names(**variables) -> list[str]:
            return [node["name"] for node in nodes(run(staff_client, LIST_QUERY, **variables))]

        assert names(group="accounts") == ["tests/welcome"]
        assert names(q="code") == ["tests/text-only"]
        assert names(q="WELCOME") == ["tests/welcome"]
        assert names(isEditable=True) == ["tests/welcome"]
        assert names(isEditable=False) == ["tests/text-only"]
        assert names(isCustomized=True) == []

        welcome.subject = "Custom"
        welcome.save()
        assert names(isCustomized=True) == ["tests/welcome"]
        assert names(isCustomized=False) == ["tests/text-only"]


class TestPreview:
    def test_preview_unsaved_text(self, welcome, staff_client) -> None:
        welcome.subject = "Saved {{ site_name }}"
        welcome.save()

        content = run(
            staff_client,
            PREVIEW_QUERY,
            id=welcome.relay_id,
            plainTextContent="Unsaved {{ user.first_name }}",
        )
        preview = content["data"]["node"]["preview"]
        assert preview == {
            "subject": "Saved Example",
            "bodyText": "Unsaved Ada",
            "bodyHtml": "<p>Unsaved Ada</p>",
        }

        # a blank argument previews the default, not the saved text
        content = run(staff_client, PREVIEW_QUERY, id=welcome.relay_id, subject="")
        assert content["data"]["node"]["preview"]["subject"] == "Welcome, Ada to Example"

    def test_preview_invalid_text(self, welcome, staff_client) -> None:
        content = run(staff_client, PREVIEW_QUERY, id=welcome.relay_id, subject="{{ secret }}")
        assert content["errors"][0]["message"] == "Unknown placeholder “secret”."
        assert content["errors"][0]["extensions"]["code"] == "invalid_template"

    def test_preview_render_failure(self, welcome, staff_client, email_template_files) -> None:
        email_template_files({"emails/tests/welcome.body.txt.j2": "{{ 1 / 0 }}"})
        content = run(staff_client, PREVIEW_QUERY, id=welcome.relay_id)
        assert content["errors"][0]["extensions"]["code"] == "preview_failed"


class TestUpdate:
    def test_needs_change_permission(self, welcome) -> None:
        client = client_for("view_emailtemplate")
        content = run(client, UPDATE_MUTATION, input={"id": welcome.relay_id, "subject": "x"})
        assert content["errors"][0]["extensions"]["code"] == "permission_required"

    def test_anonymous(self, welcome, graphql_client) -> None:
        content = graphql_client(
            UPDATE_MUTATION, variables={"input": {"id": welcome.relay_id, "subject": "x"}}
        ).json()
        assert content["errors"][0]["message"] == "authentication required"

    def test_missing_template(self, welcome, staff_client) -> None:
        relay_id = welcome.relay_id
        welcome.delete()
        content = run(staff_client, UPDATE_MUTATION, input={"id": relay_id, "subject": "x"})
        assert content["errors"][0]["extensions"]["code"] == "not_found"

    def test_update_and_reset(self, welcome, staff_client) -> None:
        content = run(
            staff_client,
            UPDATE_MUTATION,
            input={"id": welcome.relay_id, "subject": "Hi {{ user.first_name }} & co"},
        )
        payload = content["data"]["emailTemplateUpdate"]
        assert payload["errors"] is None
        assert payload["emailTemplate"]["subject"] == "Hi {{ user.first_name }} & co"
        assert payload["emailTemplate"]["isCustomized"] is True
        assert payload["emailTemplate"]["previewSubject"] == "Hi Ada & co"

        content = run(staff_client, UPDATE_MUTATION, input={"id": welcome.relay_id, "subject": ""})
        payload = content["data"]["emailTemplateUpdate"]
        assert payload["emailTemplate"]["subject"] == ""
        assert payload["emailTemplate"]["isCustomized"] is False
        welcome.refresh_from_db()
        assert welcome.subject == ""

    def test_rejects_non_editable_and_invalid_text(self, welcome, staff_client) -> None:
        content = run(
            staff_client,
            UPDATE_MUTATION,
            input={
                "id": welcome.relay_id,
                "subject": "{{ secret }}" + "x" * 300,
                "htmlContent": "<p>x</p>",
            },
        )
        payload = content["data"]["emailTemplateUpdate"]
        assert payload["emailTemplate"] is None
        errors = {error["field"]: error["messages"] for error in payload["errors"]}
        assert errors == {
            "subject": ["Unknown placeholder “secret”.", "Use at most 255 characters."],
            "htmlContent": ["This part of the email cannot be edited."],
        }
        welcome.refresh_from_db()
        assert not welcome.subject


class TestSendTest:
    def test_sends_to_own_address_only(self, welcome, staff_client, staff_user, outbox) -> None:
        content = run(
            staff_client,
            SEND_TEST_MUTATION,
            input={"id": welcome.relay_id, "subject": "Draft {{ user.first_name }}"},
        )
        assert content["data"]["emailTemplateSendTest"]["sentTo"] == staff_user.email
        assert len(outbox) == 1
        assert outbox[0].to == [staff_user.email]
        assert outbox[0].subject == "[Test] Draft Ada"
        assert outbox[0].body == "Hi Ada, A & B"
        welcome.refresh_from_db()
        assert not welcome.subject  # unsaved text is not saved

    def test_needs_permission(self, welcome, outbox) -> None:
        client = client_for("view_emailtemplate", "change_emailtemplate")
        content = run(client, SEND_TEST_MUTATION, input={"id": welcome.relay_id})
        assert content["errors"][0]["extensions"]["code"] == "permission_required"
        assert outbox == []

    def test_rate_limited(self, welcome, staff_client, outbox, settings) -> None:
        settings.BASEAPP_MESSAGE_TEMPLATES_TEST_SEND_LIMIT = "2/h"
        for _ in range(2):
            content = run(staff_client, SEND_TEST_MUTATION, input={"id": welcome.relay_id})
            assert content["data"]["emailTemplateSendTest"]["sentTo"]
        content = run(staff_client, SEND_TEST_MUTATION, input={"id": welcome.relay_id})
        assert content["errors"][0]["extensions"]["code"] == "rate_limited"
        assert len(outbox) == 2

    def test_custom_sender(self, welcome, staff_client, staff_user, outbox, settings) -> None:
        sent = []
        settings.BASEAPP_MESSAGE_TEMPLATES_TEST_SENDER = (
            lambda email, *, template, user: sent.append((email.subject, template, user.pk))
        )
        run(staff_client, SEND_TEST_MUTATION, input={"id": welcome.relay_id})
        assert sent == [("[Test] Welcome, Ada to Example", "tests/welcome", staff_user.pk)]
        assert outbox == []

    def test_field_errors(self, welcome, staff_client, outbox) -> None:
        content = run(
            staff_client, SEND_TEST_MUTATION, input={"id": welcome.relay_id, "subject": "{% if %}"}
        )
        payload = content["data"]["emailTemplateSendTest"]
        assert payload["sentTo"] is None
        assert payload["errors"][0]["field"] == "subject"
        assert outbox == []

    def test_render_failure(self, welcome, staff_client, email_template_files, outbox) -> None:
        email_template_files({"emails/tests/welcome.body.txt.j2": "{{ 1 / 0 }}"})
        content = run(staff_client, SEND_TEST_MUTATION, input={"id": welcome.relay_id})
        assert content["errors"][0]["extensions"]["code"] == "preview_failed"
        assert outbox == []

    def test_user_without_email(self, welcome, staff_client, staff_user) -> None:
        type(staff_user).objects.filter(pk=staff_user.pk).update(email="")
        content = run(staff_client, SEND_TEST_MUTATION, input={"id": welcome.relay_id})
        assert content["errors"][0]["extensions"]["code"] == "no_email"
