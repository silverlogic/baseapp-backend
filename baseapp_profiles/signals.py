from django.apps import apps
from django.dispatch import Signal

from .models import update_or_create_profile


def create_profile_url_path(instance, created, **kwargs) -> None:
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


def update_user_profile(instance, created, **kwargs) -> None:
    """
    Deprecated: profile creation is now handled by a pgtrigger INSERT trigger.
    Kept for backwards compatibility with projects that have not yet added
    `profile_owner_sql` to their User model and generated the corresponding migration.

    Connect via: post_save.connect(update_user_profile, sender=User)
    """
    if not created:
        return
    # The DB trigger may have already created and linked the profile. Refresh so
    # the Python instance reflects the DB state before deciding whether to act.
    instance.refresh_from_db(fields=["profile"])
    if instance.profile_id:
        return
    update_or_create_profile(instance, instance, f"{instance.first_name} {instance.last_name}")


# Membership and invitation lifecycle. Every signal is sent with `sender` set to the
# concrete ProfileUserRole model and `instance` set to the row, once the surrounding
# transaction has committed. `by` is the user who acted, or None for system actions.

# Kwargs: instance, inviter (the user named in the email, may be None)
invitation_sent = Signal()

# Kwargs: instance, user, created_user (True when the invitee signed up while accepting)
invitation_accepted = Signal()

# Kwargs: instance, user
invitation_declined = Signal()

# Kwargs: instance, by. With invitation history off the row is already deleted.
invitation_cancelled = Signal()

# Kwargs: instance
invitation_expired = Signal()

# Kwargs: instance, old_role, new_role, by
member_role_changed = Signal()

# Kwargs: instance, by
member_deactivated = Signal()

# Kwargs: instance, by
member_reactivated = Signal()

# Kwargs: instance, by. The row is already deleted.
member_removed = Signal()
