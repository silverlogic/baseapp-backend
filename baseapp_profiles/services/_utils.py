import logging

import swapper
from django.db import models, transaction
from django.dispatch import Signal

logger = logging.getLogger(__name__)


def send_on_commit(signal: Signal, instance: models.Model, **kwargs) -> None:
    """
    Send a membership lifecycle `signal` once the current transaction commits.

    Receivers typically notify someone; they must not act on a change that is rolled back.
    Outside a transaction the signal is sent straight away.

    By then the change is saved, so a receiver that raises is logged rather than failing
    the request (or keeping the other receivers, and the signals queued behind this one,
    from running).
    """
    ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")

    def send() -> None:
        results = signal.send_robust(sender=ProfileUserRole, instance=instance, **kwargs)
        for receiver, result in results:
            if isinstance(result, Exception):
                logger.error(
                    "Membership signal receiver %r failed for row %s",
                    receiver,
                    instance.pk,
                    exc_info=result,
                )

    transaction.on_commit(send)
