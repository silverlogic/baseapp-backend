from .models import update_or_create_profile


def update_user_profile(instance, created, **kwargs):
    """
    Call django.db.models.signals.post_save.connect(update_user_profile, sender=User)
    to automatically create a user profile when an instance of User is saved for the first time
    """

    update_or_create_profile(instance, instance, f"{instance.first_name} {instance.last_name}")
