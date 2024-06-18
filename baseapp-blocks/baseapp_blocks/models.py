import swapper

from django.contrib.contenttypes.fields import GenericRelation
from django.db import models

from baseapp_blocks.base import AbstractBaseBlock


class Block(AbstractBaseBlock):
    class Meta:
        unique_together = [
            ("actor_content_type", "actor_object_id", "target_content_type", "target_object_id")
        ]

        swappable = swapper.swappable_setting("baseapp_blocks", "Block")


SwappableBlock = swapper.load_model("baseapp_blocks", "Block", required=False, require_ready=False)


class BlockableModel(models.Model):
    blockers = GenericRelation(
        SwappableBlock,
        content_type_field="target_content_type",
        object_id_field="target_object_id",
    )
    blocking = GenericRelation(
        SwappableBlock,
        content_type_field="actor_content_type",
        object_id_field="actor_object_id",
    )
    blockers_count = models.PositiveIntegerField(db_default=0, editable=False)
    blocking_count = models.PositiveIntegerField(db_default=0, editable=False)

    class Meta:
        abstract = True
