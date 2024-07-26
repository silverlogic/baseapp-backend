import swapper
from django.apps import apps
from django.contrib.contenttypes.models import ContentType

if apps.is_installed("avatar"):
    from avatar.models import Avatar
else:
    Avatar = None


def update_user_profile(instance, **kwargs):
    Profile = swapper.load_model("baseapp_profiles", "Profile")
    target_content_type = ContentType.objects.get_for_model(instance)

    profile_image = None

    if apps.is_installed("avatar"):
        avatar = Avatar.objects.filter(user=instance).order_by("-date_uploaded").first()
        if avatar is not None:
            profile_image = avatar.avatar

    name = instance.get_full_name()
    profile, created = Profile.objects.get_or_create(
        owner=instance,
        target_content_type=target_content_type,
        target_object_id=instance.pk,
        defaults=dict(
            name=name,
            image=profile_image,
        ),
    )

    if not created:
        profile.name = name
        profile.image = profile_image
        profile.save(update_fields=["name", "image"])
    else:
        instance.profile = profile
        instance.save(update_fields=["profile"])
