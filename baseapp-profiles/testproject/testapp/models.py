from baseapp_auth.models import AbstractUser
from django.db.models.signals import post_save
from django.utils import timezone
from model_utils import FieldTracker

from baseapp_profiles.models import ProfilableModel
from baseapp_profiles.signals import update_user_profile


class User(AbstractUser, ProfilableModel):
    # FieldTracker doesn't work with abstract model classes
    tracker = FieldTracker(fields=["is_superuser", "password"])

    def save(self, *args, **kwargs):
        with self.tracker:
            if self.tracker.has_changed("password"):
                self.password_changed_date = timezone.now()
            super().save(*args, **kwargs)


post_save.connect(update_user_profile, sender=User)
