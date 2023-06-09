from unittest.mock import MagicMock

from django.utils import timezone

import pytest
from constance.test import override_config
from freezegun import freeze_time

from baseapp_auth import tasks
from testproject.testapp.models import User

import tests.factories as f

pytestmark = pytest.mark.django_db


def test_user_str():
    user = User(email="john@gmail.com")
    assert str(user) == "john@gmail.com"


def test_user_get_short_name():
    user = User(email="john@gmail.com")
    assert user.get_short_name() == "john@gmail.com"


def test_user_get_full_name():
    user = User(first_name="John", last_name="Doe", email="john@gmail.com")
    assert user.get_full_name() == "John Doe"


def test_user_get_full_name_as_email():
    """
    User instance without name returns email, so names in django returns e-mail
    (which is required) in order to debug.
    """
    user = User(email="john@gmail.com")
    assert user.get_full_name() == "john@gmail.com"


@override_config(USER_PASSWORD_EXPIRATION_INTERVAL=1)
def test_user_only_notified_once_for_expired_password():
    user = f.UserFactory()
    user.password_changed_date = timezone.now() - timezone.timedelta(days=1)
    user.save()

    mock = MagicMock()
    tasks.send_password_expired_email = mock

    with freeze_time((timezone.now() - timezone.timedelta(days=1)).strftime("%Y-%m-%d")):
        tasks.notify_users_is_password_expired()
        assert mock.call_count == 0
        mock.reset_mock()

    with freeze_time(timezone.now().strftime("%Y-%m-%d")):
        tasks.notify_users_is_password_expired()
        assert mock.call_count == 1
        mock.reset_mock()

    with freeze_time((timezone.now() + timezone.timedelta(days=1)).strftime("%Y-%m-%d")):
        tasks.notify_users_is_password_expired()
        assert mock.call_count == 0
        mock.reset_mock()
