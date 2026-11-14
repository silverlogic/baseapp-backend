from collections.abc import Callable, Generator

import pytest
from django.dispatch import Signal

from baseapp_core.graphql.testing.fixtures import *  # noqa
from baseapp_core.plugins.tests.fixtures import with_disabled_apps  # noqa: F401
from baseapp_core.tests.fixtures import *  # noqa


@pytest.fixture
def signal_recorder() -> Generator[Callable[[Signal], list[dict]], None, None]:
    """
    `record(signal)` connects a receiver and returns the list it appends each call's
    kwargs (plus `sender`) to. Receivers are disconnected after the test.
    """
    connected = []

    def record(signal: Signal) -> list[dict]:
        calls = []

        def receiver(sender, **kwargs) -> None:
            calls.append({"sender": sender, **kwargs})

        signal.connect(receiver, weak=False)
        connected.append((signal, receiver))
        return calls

    yield record
    for signal, receiver in connected:
        signal.disconnect(receiver)
