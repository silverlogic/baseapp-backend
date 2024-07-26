import swapper
from django.db import models

from baseapp_blocks.base import AbstractBaseBlock


class Block(AbstractBaseBlock):
    class Meta:
        indexes = [
            models.Index(fields=["target", "actor"]),
        ]
        unique_together = [("actor", "target")]

        swappable = swapper.swappable_setting("baseapp_blocks", "Block")


SwappableBlock = swapper.load_model("baseapp_blocks", "Block", required=False, require_ready=False)


class BlockableModel(models.Model):
    blockers_count = models.PositiveIntegerField(default=0, editable=False)
    blocking_count = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        abstract = True
