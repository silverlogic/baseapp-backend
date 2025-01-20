from unittest.mock import patch

import pytest
import swapper
from baseapp_comments.tests.factories import CommentFactory
from baseapp_core.tests.factories import UserFactory
from django.test import override_settings

from .factories import ReactionFactory

pytestmark = pytest.mark.django_db

Reaction = swapper.load_model("baseapp_reactions", "Reaction")
Notification = swapper.load_model("notifications", "Notification")


def test_user_receives_notification_when_reaction_is_created(graphql_client):
    """
    Test that a user receives a notification when a reaction is created on their comment.

    This test verifies the notification mechanism for comment reactions by:
    1. Creating a user and a comment associated with that user
    2. Enabling reaction notifications
    3. Mocking the notification sending task
    4. Creating a reaction on the comment
    5. Asserting that the notification task was called with correct arguments

    Args:
        graphql_client: A GraphQL client fixture for testing

    Checks:
        - Notification task is called when a reaction is created
        - Notification task receives the correct reaction and user identifiers
    """
    user = UserFactory()
    target = CommentFactory(user=user)

    with override_settings(BASEAPP_REACTIONS_ENABLE_NOTIFICATIONS=True):
        with patch(
            "baseapp.reactions.notifications.send_reaction_created_notification.delay"
        ) as mock:
            reaction = ReactionFactory(target=target)
            assert mock.called
            assert mock.call_args.args == (reaction.pk, user.id)
