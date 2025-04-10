import pytest
from django.conf import settings
from django.utils.module_loading import import_string


@pytest.mark.parametrize("schedule", settings.CELERY_BEAT_SCHEDULE.values())
def test_celery_beat_tasks_exist(schedule):
    """
    Tasks added in celery exists in settings exists in the code, so it avoids
    when a developer has a beat working but fail when push to a live server
    in case it is not detected by a worker.
    """

    try:
        import_string(schedule["task"])
    except ImportError:
        pytest.fail('celery beat task "{}" does not exist.'.format(schedule["task"]))


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
