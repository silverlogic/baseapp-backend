import pytest
from django.test import override_settings

import baseapp_auth.tests.helpers as h

from ...emails import remove_superuser_notification_email, send_password_expired_email

UserFactory = h.get_user_factory()

pytestmark = pytest.mark.django_db


def test_remove_superuser_notification_email(outbox):
    UserFactory(is_superuser=True)
    user = UserFactory(is_superuser=True)
    assigner = UserFactory(is_superuser=True)
    remove_superuser_notification_email(user, assigner)
    user.refresh_from_db()
    assert len(outbox) == 1


@override_settings(FRONT_CHANGE_EXPIRED_PASSWORD_URL="https://example.com/change/{token}")
def test_send_password_expired_email(outbox):
    user = UserFactory()
    send_password_expired_email(user)
    assert len(outbox) == 1
    assert outbox[0].to == [user.email]
