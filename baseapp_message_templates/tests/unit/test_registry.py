import pytest
from django.core.exceptions import ImproperlyConfigured
from django.template import TemplateDoesNotExist

import baseapp_message_templates.tests.factories as f
from baseapp_message_templates.registry import (
    Placeholder,
    email_templates,
    get_default_source,
    get_sample_context,
    is_customized,
    preview_email_template,
    register_email_template,
    render_email_template,
    validate_override,
)

pytestmark = pytest.mark.django_db


def base_context(recipient: str | None) -> dict:
    return {"site_name": "Example", "recipient": recipient}


def register_welcome(**kwargs) -> None:
    options = {
        "label": "Welcome",
        "group": "accounts",
        "placeholders": [
            Placeholder("user.first_name", help="First name", sample="Ada"),
            "company",
        ],
        "editable": ("subject", "plain_text_content"),
    }
    options.update(kwargs)
    register_email_template("tests/welcome", **options)


CONTEXT = {"user": {"first_name": "Grace"}, "site_name": "Site", "company": "A & B"}


class TestRegistration:
    def test_rejects_unknown_editable_part(self) -> None:
        with pytest.raises(ImproperlyConfigured):
            register_email_template("x", label="X", editable=("body",))

    def test_registering_again_replaces(self) -> None:
        register_email_template("x", label="First")
        register_email_template("x", label="Second", group="g")
        assert [t.label for t in email_templates.list()] == ["Second"]
        assert email_templates.list(group="g")[0].name == "x"
        assert email_templates.list(group="other") == []
        email_templates.unregister("x")
        assert not email_templates.is_registered("x")

    def test_string_placeholders_become_placeholders(self) -> None:
        template = register_email_template("x", label="X", placeholders=["order.number"])
        assert template.placeholders == (Placeholder("order.number"),)
        assert template.placeholder_roots == frozenset({"order"})


class TestRenderFiles:
    def test_unregistered_name_renders_files_by_pattern(self, email_template_files) -> None:
        rendered = render_email_template("tests/welcome", CONTEXT)

        # whitespace collapsed in the subject only
        assert rendered.subject == "Welcome, Grace to Site"
        assert rendered.body_text == "Hi Grace, A & B"
        assert rendered.body_html == "<p>Hi Grace, A &amp; B</p>"
        assert rendered.customized == frozenset()

    def test_missing_html_file_renders_empty(self, email_template_files) -> None:
        rendered = render_email_template("tests/text-only", {"code": "42"})
        assert rendered.subject == "Text only 42"
        assert rendered.body_html == ""

    def test_unregistered_name_ignores_overrides(self, email_template_files) -> None:
        rendered = render_email_template(
            "tests/text-only", {"code": "1"}, overrides={"subject": "Nope"}
        )
        assert rendered.subject == "Text only 1"

    def test_fallback(self, email_template_files) -> None:
        rendered = render_email_template("tests/missing", {"code": "7"}, fallback="tests/default")
        assert rendered.subject == "Default subject"
        assert rendered.body_text == "Default body 7"

    def test_missing_without_fallback_raises(self, email_template_files) -> None:
        with pytest.raises(TemplateDoesNotExist):
            render_email_template("tests/missing", {})
        with pytest.raises(TemplateDoesNotExist):
            render_email_template("tests/missing", {}, fallback="tests/also-missing")

    def test_registered_explicit_paths(self, email_template_files) -> None:
        register_email_template(
            "custom",
            label="Custom",
            subject_template="emails/tests/text-only.subject.txt.j2",
            text_template="emails/tests/default.body.txt.j2",
            editable=(),
        )
        rendered = render_email_template("custom", {"code": "9"})
        assert rendered.subject == "Text only 9"
        assert rendered.body_text == "Default body 9"

    def test_file_pattern_setting(self, email_template_files, settings) -> None:
        settings.BASEAPP_MESSAGE_TEMPLATES_FILE_PATTERNS = {
            "subject": "emails/tests/{name}.subject.txt.j2",
            "text": "emails/tests/{name}.body.txt.j2",
        }
        rendered = render_email_template("text-only", {"code": "3"})
        assert rendered.body_text == "Your code is 3"


class TestRenderOverrides:
    def test_precedence_per_part(self, email_template_files) -> None:
        register_welcome()
        assert render_email_template("tests/welcome", CONTEXT).subject == "Welcome, Grace to Site"

        row = f.EmailTemplateFactory(
            name="tests/welcome", subject="Hello {{ user.first_name }}", plain_text_content=""
        )
        rendered = render_email_template("tests/welcome", CONTEXT)
        assert rendered.subject == "Hello Grace"
        assert rendered.body_text == "Hi Grace, A & B"  # blank row field -> file
        assert rendered.customized == frozenset({"subject"})

        rendered = render_email_template(
            "tests/welcome", CONTEXT, overrides={"subject": "Per send", "plain_text_content": " "}
        )
        assert rendered.subject == "Per send"
        assert rendered.body_text == "Hi Grace, A & B"

        row.subject = ""
        row.save()
        assert render_email_template("tests/welcome", CONTEXT).customized == frozenset()

    def test_only_editable_parts_are_honoured(self, email_template_files) -> None:
        register_welcome(editable=("subject",))
        f.EmailTemplateFactory(
            name="tests/welcome",
            plain_text_content="Row text",
            html_content="<p>Row html</p>",
        )
        rendered = render_email_template(
            "tests/welcome", CONTEXT, overrides={"html_content": "<p>Override</p>"}
        )
        assert rendered.body_text == "Hi Grace, A & B"
        assert rendered.body_html == "<p>Hi Grace, A &amp; B</p>"

    def test_context_restricted_to_declared_roots(self, email_template_files) -> None:
        register_welcome()
        rendered = render_email_template(
            "tests/welcome",
            {**CONTEXT, "secret": "s3cret"},
            overrides={"subject": "{{ company }} {{ secret }}"},
        )
        assert rendered.subject == "A & B"

    def test_no_autoescape_in_subject_and_text(self, email_template_files) -> None:
        register_welcome(editable=("subject", "plain_text_content", "html_content"))
        rendered = render_email_template(
            "tests/welcome",
            CONTEXT,
            overrides={
                "subject": "{{ company }} <news>",
                "plain_text_content": "Dear {{ user.first_name }} of {{ company }}",
                "html_content": "<b>{{ company }}</b> {{ body_text }}",
            },
        )
        assert rendered.subject == "A & B <news>"
        assert rendered.body_text == "Dear Grace of A & B"
        assert rendered.body_html == "<b>A &amp; B</b> Dear Grace of A &amp; B"

    def test_html_file_receives_overridden_text(self, email_template_files) -> None:
        register_welcome()
        rendered = render_email_template(
            "tests/welcome", CONTEXT, overrides={"plain_text_content": "Custom {{ company }}"}
        )
        assert rendered.body_html == "<p>Custom A &amp; B</p>"
        assert type(rendered.body_text) is str

    def test_row_passed_by_caller_is_used_without_a_query(
        self, email_template_files, django_assert_num_queries
    ) -> None:
        register_welcome()
        row = f.EmailTemplateFactory.build(name="tests/welcome", subject="Built {{ company }}")
        with django_assert_num_queries(0):
            rendered = render_email_template("tests/welcome", CONTEXT, row=row)
        assert rendered.subject == "Built A & B"

    def test_base_context(self, email_template_files, settings) -> None:
        settings.BASEAPP_MESSAGE_TEMPLATES_BASE_CONTEXT = (
            "baseapp_message_templates.tests.unit.test_registry.base_context"
        )
        register_welcome()
        rendered = render_email_template(
            "tests/welcome",
            {"user": {"first_name": "Ada"}, "company": "C"},
            overrides={"subject": "{{ site_name }} for {{ recipient }}"},
            recipient="ada@example.com",
        )
        assert rendered.subject == "Example for ada@example.com"


class TestPreview:
    def test_sample_values_and_unknown_names(self, email_template_files) -> None:
        register_welcome()
        preview = preview_email_template("tests/welcome")
        assert preview.subject == "Welcome, Ada to {{ site_name }}"
        assert preview.preview_subject == preview.subject
        assert preview.body_text == "Hi Ada, A & B"

    def test_unknown_dotted_names_in_files(self, email_template_files) -> None:
        email_template_files({"emails/tests/dotted.subject.txt.j2": "{{ order.number }}"})
        email_template_files({"emails/tests/dotted.body.txt.j2": "x"})
        register_email_template("tests/dotted", label="Dotted", editable=())
        assert preview_email_template("tests/dotted").subject == "{{ order.number }}"

    def test_unknown_names_in_overrides(self, email_template_files) -> None:
        register_welcome()
        preview = preview_email_template(
            "tests/welcome", {"subject": "{{ user.first_name }} at {{ company }}"}
        )
        assert preview.subject == "Ada at {{ company }}"
        assert preview.customized == frozenset({"subject"})

    def test_sample_context_merges_over_placeholder_samples(self, email_template_files) -> None:
        register_welcome(sample_context=lambda: {"user": {"last_name": "Lovelace"}})
        assert get_sample_context("tests/welcome") == {
            "user": {"first_name": "Ada", "last_name": "Lovelace"}
        }
        assert get_sample_context("not-registered") == {}

    def test_django_engine_files(self, email_template_files) -> None:
        email_template_files({"emails/tests/django.subject.txt": "Hi {{ user.first_name }}!"})
        register_email_template(
            "tests/django",
            label="Django",
            subject_template="emails/tests/django.subject.txt",
            text_template="emails/tests/default.body.txt.j2",
            editable=(),
        )
        assert preview_email_template("tests/django").subject == "Hi {{ user.first_name }}!"
        assert get_default_source("tests/django", "subject") == "Hi {{ user.first_name }}!"


class TestValidateOverride:
    def test_blank_is_valid(self) -> None:
        assert validate_override("anything", "subject", "  ") == []

    def test_unknown_part(self) -> None:
        with pytest.raises(ValueError):
            validate_override("anything", "body", "x")

    def test_syntax_error(self) -> None:
        register_welcome()
        errors = validate_override("tests/welcome", "subject", "{% if %}")
        assert len(errors) == 1
        assert errors[0].startswith("Template syntax error")

    def test_unknown_root(self) -> None:
        register_welcome()
        errors = validate_override(
            "tests/welcome", "subject", "{{ user.first_name }} {{ secret.key|upper }}"
        )
        assert errors == ["Unknown placeholder “secret”."]

    def test_names_bound_by_tags_and_builtins(self) -> None:
        register_welcome()
        text = (
            "{% for item in company %}{{ forloop.counter }}{{ item }}{% endfor %}"
            "{% with name=user.first_name %}{{ name|default:company }}{% endwith %}"
            "{% if user.first_name and not company %}{{ True }}{% endif %}"
            "{% firstof user.first_name 'x' as who %}{{ who }}"
            "{% filter upper %}hi{% endfilter %}{% now 'Y' %}"
            "{% comment %}{{ ignored }}{% endcomment %}"
        )
        assert validate_override("tests/welcome", "plain_text_content", text) == []

    def test_disallowed_tags(self) -> None:
        register_welcome()
        errors = validate_override("tests/welcome", "subject", "{% debug %}")
        assert errors == ["The “debug” tag is not allowed here."]

    def test_body_text_only_in_html(self) -> None:
        register_welcome()
        assert validate_override("tests/welcome", "html_content", "{{ body_text }}") == []
        assert validate_override("tests/welcome", "subject", "{{ body_text }}") == [
            "Unknown placeholder “body_text”."
        ]

    def test_base_context_keys_are_allowed(self, settings) -> None:
        settings.BASEAPP_MESSAGE_TEMPLATES_BASE_CONTEXT = (
            "baseapp_message_templates.tests.unit.test_registry.base_context"
        )
        register_welcome()
        assert validate_override("tests/welcome", "subject", "{{ site_name }}") == []

    def test_unregistered_name_checks_syntax_and_tags_only(self) -> None:
        assert validate_override("not-registered", "subject", "{{ anything }}") == []
        assert validate_override("not-registered", "subject", "{% load static %}") == [
            "The “load” tag is not allowed here."
        ]


class TestRows:
    def test_default_source_is_raw(self, email_template_files) -> None:
        register_welcome()
        assert get_default_source("tests/welcome", "subject") == (
            "{% if user.first_name %}Welcome, {{ user.first_name }}{% else %}Welcome{% endif %}\n"
            "  to   {{ site_name }}"
        )
        assert get_default_source("tests/welcome", "html_content") == "<p>{{ body_text|e }}</p>"
        assert get_default_source("tests/missing", "subject") is None

    def test_is_customized(self) -> None:
        register_welcome()
        row = f.EmailTemplateFactory.build(name="tests/welcome", html_content="<p>x</p>")
        assert not is_customized(row)  # html is not editable
        row.plain_text_content = "Body"
        assert is_customized(row)
        assert not is_customized(f.EmailTemplateFactory.build(name="other", subject="x"))
