from unittest.mock import patch

import pytest
import swapper
from baseapp_core.tests.factories import UserFactory
from django.test import override_settings

from .factories import ReactionFactory

pytestmark = pytest.mark.django_db

Reaction = swapper.load_model("baseapp_reactions", "Reaction")
Notification = swapper.load_model("notifications", "Notification")


def test_user_receieve_notification_when_reaction_is_created():
    user = UserFactory()
    friend = UserFactory()

    target = ReactionFactory(user=user)

    with override_settings(BASEAPP_REACTIONS_ENABLE_NOTIFICATIONS=True):
        with patch(
            "baseapp_reactions.notifications.send_reaction_created_notification.delay"
        ) as mock:
            reaction = ReactionFactory(target=target, user=friend)
            assert mock.called
            assert mock.call_args.args == (reaction.pk, user.id)
