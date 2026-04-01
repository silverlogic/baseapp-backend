from django.apps import apps

from .models import update_or_create_profile


def create_profile_url_path(instance, created, **kwargs):
    """
    After a ProfilableModel instance is created, the DB trigger has already created
    the Profile row and set profile_id. This signal handles URL path creation, which
    requires Python-level string manipulation and collision detection.

    Connect via: post_save.connect(create_profile_url_path, sender=YourModel)
    """
    if not created:
        return
    if not apps.is_installed("baseapp_pages"):
        return
    instance.refresh_from_db(fields=["profile"])
    if instance.profile_id:
        instance.profile.create_url_path()


def update_user_profile(instance, created, **kwargs):
    """
    Deprecated: profile creation is now handled by a pgtrigger INSERT trigger.
    Kept for backwards compatibility with projects that have not yet added
    `profile_owner_sql` to their User model and generated the corresponding migration.

    Connect via: post_save.connect(update_user_profile, sender=User)
    """
    if created:
        update_or_create_profile(instance, instance, f"{instance.first_name} {instance.last_name}")
