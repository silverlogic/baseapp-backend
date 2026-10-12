import pytest
from django.utils import translation

import baseapp_auth.tests.helpers as h
from baseapp_auth.emails import (
    new_superuser_notification_email,
    send_password_expired_email,
)

pytestmark = pytest.mark.django_db

UserFactory = h.get_user_factory()


def translated(language: str, msgid: str) -> str:
    with translation.override(language):
        text = translation.gettext(msgid)
    assert text != msgid, f"{msgid!r} has no {language} translation"
    return text


@pytest.mark.parametrize("language", ["es", "pt-br"])
def test_password_expired_email_uses_recipient_language(language, outbox) -> None:
    user = UserFactory(preferred_language=language)

    send_password_expired_email(user)

    assert len(outbox) == 1
    assert outbox[0].subject == translated(language, "Password Expired")
    assert "Password Expired" not in outbox[0].body
    assert translated(language, "Hello,") in outbox[0].body


def test_email_language_is_restored_after_sending(outbox) -> None:
    translation.activate("en")
    send_password_expired_email(UserFactory(preferred_language="es"))
    assert translation.get_language() == "en"


def test_superuser_broadcast_groups_recipients_by_language(outbox) -> None:
    assigner = UserFactory(is_superuser=True, preferred_language="en")
    new_superuser = UserFactory(is_superuser=True, preferred_language="en")
    spanish = UserFactory(is_superuser=True, preferred_language="es")
    english = UserFactory(is_superuser=True, preferred_language="en")

    new_superuser_notification_email(new_superuser, assigner)

    by_recipient = {tuple(mail.to): mail.subject for mail in outbox}
    assert by_recipient == {
        (spanish.email,): translated("es", "A New Superuser Has Been Added"),
        (english.email,): "A New Superuser Has Been Added",
    }
