import swapper
from django.db import migrations


class Migration(migrations.Migration):
    def forwards_func(apps, _):
        Profile = swapper.load_model("baseapp_profiles", "Profile")
        Comment = apps.get_model("baseapp_comments", "Comment")
        CommentEvent = apps.get_model("baseapp_comments", "CommentEvent")

        for comment in Comment.objects.filter(
            new_profile_id__isnull=True, profile_object_id__isnull=False
        ):
            profile = Profile.objects.get(
                target_content_type_id=comment.profile_content_type_id,
                target_object_id=comment.profile_object_id,
            )

            comment.new_profile = profile
            comment.save(update_fields=["new_profile"])

        for comment in CommentEvent.objects.filter(
            new_profile_id__isnull=True, profile_object_id__isnull=False
        ):
            profile = Profile.objects.get(
                target_content_type_id=comment.profile_content_type_id,
                target_object_id=comment.profile_object_id,
            )

            comment.new_profile = profile
            comment.save(update_fields=["new_profile"])

    def reverse_func(apps, _):
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
