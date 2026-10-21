from django.db import models

from baseapp.email_log.models import AbstractEmailLog


class EmailLog(AbstractEmailLog):
    # A project column, so the package's tests run against a swapped model with extras.
    extra_field = models.CharField(max_length=100, blank=True)

    class Meta(AbstractEmailLog.Meta):
        pass
