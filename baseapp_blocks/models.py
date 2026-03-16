import swapper
from django.db import models

from baseapp_blocks.base import AbstractBaseBlock
from baseapp_core.plugins import apply_if_installed


class Block(AbstractBaseBlock):
    class Meta:
        indexes = [
            models.Index(
                fields=apply_if_installed(
                    "baseapp_profiles",
                    ["target", "actor"],
                    ["target", "user"],
                )
            ),
        ]
        unique_together = [
            apply_if_installed(
                "baseapp_profiles",
                ("actor", "target"),
                ("user", "target"),
            )
        ]

        swappable = swapper.swappable_setting("baseapp_blocks", "Block")

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import BlockObjectType

        return BlockObjectType


class BlockableModel(models.Model):
    blockers_count = models.PositiveIntegerField(default=0, editable=False)
    blocking_count = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        abstract = True
