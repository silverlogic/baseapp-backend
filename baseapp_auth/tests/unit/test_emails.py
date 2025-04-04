import pytest

import baseapp_auth.tests.helpers as h

from ...emails import remove_superuser_notification_email

UserFactory = h.get_user_factory()

pytestmark = pytest.mark.django_db


def test_remove_superuser_notification_email(outbox):
    UserFactory(is_superuser=True)
    user = UserFactory(is_superuser=True)
    assigner = UserFactory(is_superuser=True)
    remove_superuser_notification_email(user, assigner)
    user.refresh_from_db()
    assert len(outbox) == 1
