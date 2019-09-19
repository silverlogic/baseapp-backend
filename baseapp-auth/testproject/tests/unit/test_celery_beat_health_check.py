from django.conf import settings
from django.utils.module_loading import import_string

import pytest


@pytest.mark.parametrize("schedule", settings.CELERY_BEAT_SCHEDULE.values())
def test_celery_beat_tasks_exist(schedule):
    try:
        import_string(schedule["task"])
    except ImportError:
        pytest.fail('celery beat task "{}" does not exist.'.format(schedule["task"]))
