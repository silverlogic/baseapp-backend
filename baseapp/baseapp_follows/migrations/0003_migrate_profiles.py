import swapper
from django.db import migrations

from baseapp_core.swappable import get_apps_model


class Migration(migrations.Migration):
    def forwards_func(apps, _):
        Profile = get_apps_model(apps, "baseapp_profiles", "Profile")
        Follow = get_apps_model(apps, "baseapp_follows", "Follow")

        if not swapper.is_swapped("baseapp_follows", "Follow"):
            for follow in Follow.objects.filter(
                new_actor__isnull=True, actor_object_id__isnull=False
            ):
                follow.new_actor = Profile.objects.get(
                    target_content_type_id=follow.actor_content_type_id,
                    target_object_id=follow.actor_object_id,
                )

                follow.new_target = Profile.objects.get(
                    target_content_type_id=follow.target_content_type_id,
                    target_object_id=follow.target_object_id,
                )

                if follow.actor_content_type.model == "user":
                    follow.user_id = follow.actor_object_id

                follow.save(update_fields=["new_actor", "new_target", "user_id"])

    def reverse_func(apps, _):
        Follow = get_apps_model(apps, "baseapp_follows", "Follow")

        if not swapper.is_swapped("baseapp_follows", "Follow"):
            for follow in Follow.objects.filter(
                new_actor__isnull=False, actor_object_id__isnull=True
            ):
                follow.actor_content_type = follow.new_actor.target_content_type
                follow.actor_object_id = follow.new_actor.target_object_id

                follow.target_content_type = follow.new_target.target_content_type
                follow.target_object_id = follow.new_target.target_object_id

                follow.save(
                    update_fields=[
                        "actor_content_type",
                        "actor_object_id",
                        "target_content_type",
                        "target_object_id",
                    ]
                )

    dependencies = [
        ("baseapp_follows", "0002_follow_new_actor_follow_new_target"),
    ]

    operations = [
        migrations.RunPython(forwards_func, reverse_func),
    ]
