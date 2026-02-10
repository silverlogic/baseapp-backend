from django.db import models

from baseapp_blocks.base import AbstractBaseBlock


class Block(AbstractBaseBlock):
    class Meta:
        indexes = [
            models.Index(fields=["target", "actor"]),
        ]
        unique_together = [("actor", "target")]
