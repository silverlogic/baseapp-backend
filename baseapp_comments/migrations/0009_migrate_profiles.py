import logging

import swapper
from django.db import migrations

from baseapp_core.swappable import get_apps_model


class Migration(migrations.Migration):
    def forwards_func(apps, _):
        Profile = get_apps_model(apps, "baseapp_profiles", "Profile")
        Comment = get_apps_model(apps, "baseapp_comments", "Comment")
        CommentEvent = apps.get_model("baseapp_comments", "CommentEvent")

        # check if swappable model is set for commment
        if not swapper.is_swapped("baseapp_comments", "Comment"):

            for comment in Comment.objects.filter(
                new_profile_id__isnull=True, profile_object_id__isnull=False
            ):
                try:
                    profile = Profile.objects.get(
                        target_content_type_id=comment.profile_content_type_id,
                        target_object_id=comment.profile_object_id,
                    )
                except Profile.DoesNotExist:
                    logging.error(
                        f"Can't find {comment.profile_content_type.model} with PK {comment.profile_object_id}"
                    )
                    continue

                comment.new_profile = profile
                comment.save(update_fields=["new_profile"])

            for comment in CommentEvent.objects.filter(
                new_profile_id__isnull=True, profile_object_id__isnull=False
            ):
                try:
                    profile = Profile.objects.get(
                        target_content_type_id=comment.profile_content_type_id,
                        target_object_id=comment.profile_object_id,
                    )
                except Profile.DoesNotExist:
                    logging.error(
                        f"Can't find {comment.profile_content_type.model} with PK {comment.profile_object_id}"
                    )
                    continue

                comment.new_profile = profile
                comment.save(update_fields=["new_profile"])

    def reverse_func(apps, _):
        if not swapper.is_swapped("baseapp_comments", "Comment"):
            Comment = apps.get_model("baseapp_comments", "Comment")
            CommentEvent = apps.get_model("baseapp_comments", "CommentEvent")

            for comment in Comment.objects.filter(
                new_profile_id__isnull=False, profile_object_id__isnull=True
            ):
                comment.profile_content_type = comment.new_profile.target_content_type
                comment.profile_object_id = comment.new_profile.target_object_id
                comment.save(update_fields=["profile_content_type", "profile_object_id"])

            for comment in CommentEvent.objects.filter(
                new_profile_id__isnull=False, profile_object_id__isnull=True
            ):
                comment.profile_content_type = comment.new_profile.target_content_type
                comment.profile_object_id = comment.new_profile.target_object_id
                comment.save(update_fields=["profile_content_type", "profile_object_id"])

    dependencies = [
        ("baseapp_comments", "0008_comment_new_profile_commentevent_new_profile_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards_func, reverse_func),
    ]
