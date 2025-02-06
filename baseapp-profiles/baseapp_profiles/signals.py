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

        name = instance.get_full_name()

        profile = Profile.objects.create(
            name=name,
            owner=instance,
            target_content_type=target_content_type,
            target_object_id=instance.pk,
        )

        instance.profile = profile
        instance.save(update_fields=["profile"])


def update_user_name(instance, created, **kwargs):
    """
    Call django.db.models.signals.post_save.connect(update_user_name, sender=Profile)
    to update the first_name of the user object associated to a Profile instance
    whenever the profile name is updated.
    """

    try:
        user = instance.user
    except ObjectDoesNotExist:
        return

    if user.first_name != instance.name:
        user.first_name = instance.name
        user.last_name = ""
        user.save(update_fields=["first_name", "last_name"])
