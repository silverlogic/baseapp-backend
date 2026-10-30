"""
Regression tests for Celery task registration in ``baseapp_auth``.

``app.autodiscover_tasks()`` only imports ``<app>.tasks`` for each installed app. The anonymize
task lives in ``baseapp_auth.rest_framework.users.tasks``, which the worker process never imported,
so every ``anonymize_and_delete_user_task`` message was discarded as unregistered
(Sentry BASEAPP-BACKEND-TEMPLATE-5D).
"""

from celery import current_app
from celery.loaders.base import find_related_module

from baseapp_auth.rest_framework.users.tasks import anonymize_and_delete_user_task

ANONYMIZE_TASK_NAME = "baseapp_auth.rest_framework.users.tasks.anonymize_and_delete_user_task"


def test_anonymize_task_is_reachable_through_autodiscovered_module() -> None:
    """The module ``autodiscover_tasks`` imports for ``baseapp_auth`` exposes the anonymize task."""
    # ``find_related_module`` is what ``autodiscover_tasks`` uses to resolve ``<app>.tasks``.
    module = find_related_module("baseapp_auth", "tasks")

    assert module is not None
    assert module.anonymize_and_delete_user_task is anonymize_and_delete_user_task


def test_anonymize_task_keeps_production_name() -> None:
    """Messages already queued with an ETA must still match the name the worker registers."""
    assert anonymize_and_delete_user_task.name == ANONYMIZE_TASK_NAME


def test_anonymize_task_is_registered_under_production_name() -> None:
    """The task registry resolves the production name to the anonymize task."""
    # ``shared_task`` returns a proxy, so compare by equality rather than identity.
    assert ANONYMIZE_TASK_NAME in current_app.tasks
    assert current_app.tasks[ANONYMIZE_TASK_NAME] == anonymize_and_delete_user_task
