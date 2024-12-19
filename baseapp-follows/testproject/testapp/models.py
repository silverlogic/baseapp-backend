from baseapp_auth.models import AbstractUser
from baseapp_follows.models import FollowableModel
from baseapp_profiles.models import ProfilableModel
from django.utils import timezone
from model_utils import FieldTracker


class User(AbstractUser, ProfilableModel, FollowableModel):
    # FieldTracker doesn't work with abstract model classes
    tracker = FieldTracker(fields=["is_superuser", "password"])

    def save(self, *args, **kwargs):
        with self.tracker:
            if self.tracker.has_changed("password"):
                self.password_changed_date = timezone.now()
            super().save(*args, **kwargs)
