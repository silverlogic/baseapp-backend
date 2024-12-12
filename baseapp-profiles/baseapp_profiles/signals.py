import swapper
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext as _
from .notifications import send_reply_created_notification


def update_user_profile(instance, **kwargs):
    Profile = swapper.load_model("baseapp_profiles", "Profile")
    target_content_type = ContentType.objects.get_for_model(instance)

    name = instance.get_full_name()

    profile, created = Profile.objects.get_or_create(
        owner=instance,
        target_content_type=target_content_type,
        target_object_id=instance.pk,
        defaults=dict(
            name=name,
        ),
    )

    if created:
        instance.profile = profile
        instance.save(update_fields=["profile"])
    else:
        profile.name = name
        profile.save(update_fields=["name"])


def notify_on_profile_update(instance, **kwargs):
    if hasattr(instance, "tracker"):
        modified = [field for field in instance.tracker.changed() if field in ["image", "biography", "banner_image"]]
        modified.sort()
        if modified:
            description = _("{user} updated {fields} your profile.").format(
                user=instance.owner.get_full_name(),
                fields=", ".join(modified),
            )
            send_reply_created_notification.delay(instance.pk, description)
