import swapper
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist


def update_user_profile(instance, created, **kwargs):
    """
    Call django.db.models.signals.post_save.connect(update_user_profile, sender=User)
    to automatically create a user profile when an instance of User is saved for the first time
    """

    if created and not instance.profile_id:
        Profile = swapper.load_model("baseapp_profiles", "Profile")
        target_content_type = ContentType.objects.get_for_model(instance)

        profile = Profile.objects.create(
            owner=instance,
            target_content_type=target_content_type,
            target_object_id=instance.pk,
        )

        instance.profile = profile
        instance.save(update_fields=["profile"])
