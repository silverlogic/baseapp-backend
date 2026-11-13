from collections.abc import Generator

import pytest
from celery import current_app

from baseapp_core.graphql.testing.fixtures import *  # noqa: F403, F401

from .fixtures import *  # noqa: F403, F401

# The settings Django's CELERY_TASK_ALWAYS_EAGER / CELERY_TASK_EAGER_PROPAGATES stand for.
_EAGER = {"task_always_eager": True, "task_eager_propagates": True}


@pytest.fixture(autouse=True)
def eager_celery() -> Generator[None, None, None]:
    """Run ``.delay()`` synchronously in the payments tests, on every thread (the
    concurrency tests), and put Celery's default app back as it was afterwards.

    Scoped to these tests rather than applied at import: reconfiguring the app when this
    conftest loads changed Celery for every other package's tests in the same session.
    """
    conf = current_app.conf
    saved = {key: conf.get(key) for key in _EAGER}
    conf.update(_EAGER)
    try:
        yield
    finally:
        conf.update(saved)
