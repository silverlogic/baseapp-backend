import pytest
from celery import current_app
from django.conf import settings
from django.utils.module_loading import import_string


@pytest.mark.parametrize("name, schedule", settings.CELERY_BEAT_SCHEDULE.items())
def test_celery_beat_tasks_exist(name, schedule):
    """
    Tasks added in celery exists in settings exists in the code, so it avoids
    when a developer has a beat working but fail when push to a live server
    in case it is not detected by a worker.
    """

    try:
        task_path = schedule["task"]
        import_string(task_path)
    except ImportError:
        pytest.fail('celery beat task "{}" does not exist.'.format(schedule["task"]))

    task = current_app.tasks.get(task_path)
    assert task is not None, (
        f"Task path '{task_path}' in beat schedule entry '{name}' is not "
        f"registered in Celery. Make sure it's decorated with @shared_task or @app.task "
        f"and imported at startup."
    )


@pytest.mark.parametrize("schedule", settings.CELERY_BEAT_SCHEDULE.values())
def test_celery_beat_tasks_have_expires(schedule):
    """
    Tasks added in celery have expiration time, so we don't have a task being
    created several times and running duplicates.
    """

    if not schedule.get("options", {}).get("expires"):
        pytest.fail(
            'celery beat task "{}" must set options.expires.  Standard rule is 75% of the schedule frequency. e.g. if task is scheduled hourly, expire after 45 min'.format(
                schedule["task"]
            )
        )
