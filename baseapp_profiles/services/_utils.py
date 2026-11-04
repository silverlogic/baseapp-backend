import swapper
from django.db import models, transaction
from django.dispatch import Signal


def send_on_commit(signal: Signal, instance: models.Model, **kwargs) -> None:
    """
    Send a membership lifecycle `signal` once the current transaction commits.

    Receivers typically notify someone; they must not act on a change that is rolled back.
    Outside a transaction the signal is sent straight away.
    """
    ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
    transaction.on_commit(lambda: signal.send(sender=ProfileUserRole, instance=instance, **kwargs))
