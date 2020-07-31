from django.conf import settings
from django.utils.module_loading import import_string

import pytest


@pytest.mark.parametrize("schedule", settings.CELERY_BEAT_SCHEDULE.values())
def test_celery_beat_tasks_exist(schedule):
    try:
        import_string(schedule["task"])
    except ImportError:
        pytest.fail('celery beat task "{}" does not exist.'.format(schedule["task"]))


@pytest.mark.parametrize("schedule", settings.CELERY_BEAT_SCHEDULE.values())
def test_celery_beat_tasks_have_expires(schedule):
    if not schedule.get("expires"):
        pytest.fail(
            'celery beat task "{}" must set expires.  Standard rule is 75% of the schedule frequency. e.g. if task is scheduled hourly, expire after 45 min'.format(
                schedule["task"]
            )
        )
