import swapper
from django.db import migrations

from baseapp_core.swappable import get_apps_model


class Migration(migrations.Migration):
    def forwards_func(apps, _):
        Block = get_apps_model(apps, "baseapp_blocks", "Block")
        Profile = get_apps_model(apps, "baseapp_profiles", "Profile")

        if not swapper.is_swapped("baseapp_blocks", "Block"):
            for block in Block.objects.filter(actor__isnull=True, actor_object_id__isnull=False):
                block.actor = Profile.objects.get(
                    target_content_type_id=block.actor_content_type_id,
                    target_object_id=block.actor_object_id,
                )

                block.target = Profile.objects.get(
                    target_content_type_id=block.target_content_type_id,
                    target_object_id=block.target_object_id,
                )

                if block.actor_content_type.model == "user":
                    block.user_id = block.actor_object_id

                block.save(update_fields=["actor", "target", "user_id"])

    def reverse_func(apps, _):
        Block = get_apps_model(apps, "baseapp_blocks", "Block")

        if not swapper.is_swapped("baseapp_blocks", "Block"):
            for block in Block.objects.filter(actor__isnull=False, actor_object_id__isnull=True):
                block.actor_content_type = block.actor.target_content_type
                block.actor_object_id = block.actor.target_object_id

                block.target_content_type = block.target.target_content_type
                block.target_object_id = block.target.target_object_id

                block.save(
                    update_fields=[
                        "actor_content_type",
                        "actor_object_id",
                        "target_content_type",
                        "target_object_id",
                    ]
                )

    dependencies = [
        ("baseapp_blocks", "0003_block_actor_block_target_alter_block_user"),
    ]

    operations = [
        migrations.RunPython(forwards_func, reverse_func),
    ]
