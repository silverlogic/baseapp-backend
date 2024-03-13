from baseapp_auth.models import AbstractUser
from django.utils import timezone
from model_utils import FieldTracker

from baseapp_follows.models import FollowableModel


class User(AbstractUser, FollowableModel):
    # FieldTracker doesn't work with abstract model classes
    tracker = FieldTracker(fields=["is_superuser", "password"])

    def save(self, *args, **kwargs):
        with self.tracker:
            if self.tracker.has_changed("password"):
                self.password_changed_date = timezone.now()
            super().save(*args, **kwargs)

    def has_permission(self, permission, obj=None):
        if permission == "follow.as_actor":
            return self == obj
        if permission == "follow.add_follow":
            return True
        if permission == "follow.delete_follow":
            return True
