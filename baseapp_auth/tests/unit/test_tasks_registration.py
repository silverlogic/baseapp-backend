import importlib

from celery import current_app


def test_anonymize_task_is_reachable_from_autodiscovered_module() -> None:
    """
    Celery's ``autodiscover_tasks()`` imports only ``baseapp_auth.tasks``, so every task
    the worker must execute has to be importable from there. The anonymize task lives in
    ``baseapp_auth.rest_framework.users.tasks``; when nothing in the worker imported that
    module, the worker rejected the message as an unregistered task and discarded it
    (Sentry BASEAPP-BACKEND-TEMPLATE-5D).
    """
    tasks_module = importlib.import_module("baseapp_auth.tasks")

    task = tasks_module.anonymize_and_delete_user_task

    # The name is what the producer puts on the wire; it must stay stable so messages
    # already queued with an ETA are still picked up.
    assert task.name == "baseapp_auth.rest_framework.users.tasks.anonymize_and_delete_user_task"
    assert task.name in current_app.tasks
