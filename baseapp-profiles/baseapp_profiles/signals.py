import swapper
from django.contrib.contenttypes.models import ContentType


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
