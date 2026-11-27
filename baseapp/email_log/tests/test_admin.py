import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client
from django.urls import reverse

from baseapp.email_log.models import get_email_log_model
from baseapp.email_log.services import (
    attach_log_metadata,
    log_channel_message,
    send_logged,
)

from .helpers import make_email

EmailLog = get_email_log_model()
User = get_user_model()

pytestmark = pytest.mark.django_db

CHANGELIST = f"admin:{EmailLog._meta.app_label}_{EmailLog._meta.model_name}_changelist"
CHANGE = f"admin:{EmailLog._meta.app_label}_{EmailLog._meta.model_name}_change"


@pytest.fixture
def superuser() -> User:
    return User.objects.create_superuser(email="admin@example.com", password="pass1234")


@pytest.fixture
def superuser_client(superuser: User) -> Client:
    client = Client()
    client.force_login(superuser)
    return client


def test_changelist_filters_and_search(
    superuser_client: Client, failing_transport: None, settings
) -> None:
    failed = send_logged(make_email(subject="Broken"), idempotency_key=None, category="billing")
    settings.DJMAIL_REAL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    sent = send_logged(
        make_email(subject="Welcome", cc=["boss@example.com"]),
        idempotency_key=None,
        category="auth",
    )
    sms = log_channel_message(channel="sms", to="+15555550100", body_text="Code")

    def listed(**params) -> set:
        response = superuser_client.get(reverse(CHANGELIST), params)
        assert response.status_code == 200
        return {row.pk for row in response.context["cl"].result_list}

    assert listed() == {failed.pk, sent.pk, sms.pk}
    assert listed(status="failed") == {failed.pk}
    assert listed(status="queued") == {sms.pk}
    assert listed(channel__exact="sms") == {sms.pk}
    assert listed(category="auth") == {sent.pk}
    assert listed(q="Welcome") == {sent.pk}
    assert listed(q="boss@example.com") == {sent.pk}
    assert listed(q="+15555550100") == {sms.pk}


def test_change_view_shows_djmail_fields_read_only(superuser_client: Client) -> None:
    email = attach_log_metadata(
        make_email(html="<script>alert(1)</script>"), template="welcome", context={"a": 1}
    )
    email.send()
    log = EmailLog.objects.get()

    response = superuser_client.get(reverse(CHANGE, args=[log.pk]))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Your invoice" in content
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in content
    assert "<script>alert(1)</script>" not in content
    assert log.message_id in content
    assert "Failed attempts" in content
    # Nothing is editable.
    assert response.context["adminform"].form.fields == {}


def test_change_view_of_a_channel_row(superuser_client: Client) -> None:
    log = log_channel_message(channel="sms", to="+1", body_text="Code 42")

    response = superuser_client.get(reverse(CHANGE, args=[log.pk]))

    assert response.status_code == 200
    assert "Code 42" in response.content.decode()


def test_no_add_permission(superuser_client: Client) -> None:
    add_url = f"admin:{EmailLog._meta.app_label}_{EmailLog._meta.model_name}_add"
    assert superuser_client.get(reverse(add_url)).status_code == 403


def test_resend_action(superuser_client: Client, superuser: User) -> None:
    log = send_logged(make_email(), idempotency_key=None)
    sms = log_channel_message(channel="sms", to="+1", body_text="x")

    response = superuser_client.post(
        reverse(CHANGELIST),
        {"action": "resend_emails", "_selected_action": [log.pk, sms.pk]},
        follow=True,
    )

    assert response.status_code == 200
    messages = [str(message) for message in response.context["messages"]]
    assert "Resent 1 email." in messages
    assert any("Only email rows can be resent." in message for message in messages)
    copy = EmailLog.objects.get(resend_of=log)
    assert copy.sent_by == superuser
    assert len(mail.outbox) == 2
