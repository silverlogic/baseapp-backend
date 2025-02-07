from unittest.mock import patch

import pytest
import swapper
from django.test import override_settings

from baseapp_comments.tests.factories import CommentFactory
from baseapp_core.tests.factories import UserFactory

from .factories import ReactionFactory

pytestmark = pytest.mark.django_db

Reaction = swapper.load_model("baseapp_reactions", "Reaction")
Notification = swapper.load_model("notifications", "Notification")


def test_user_receives_notification_when_reaction_is_created(graphql_client):
    user = UserFactory()
    target = CommentFactory(user=user)

    with override_settings(BASEAPP_REACTIONS_ENABLE_NOTIFICATIONS=True):
        with patch(
            "baseapp_reactions.notifications.send_reaction_created_notification.delay"
        ) as mock:
            reaction = ReactionFactory(target=target)
            assert mock.called
            assert mock.call_args.args == (reaction.pk, user.id)
