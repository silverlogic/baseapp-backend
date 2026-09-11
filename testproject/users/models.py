from django.db.models.signals import post_save
from django.utils import timezone
from model_utils import FieldTracker

from baseapp_auth.models import AbstractUser
from baseapp_profiles.signals import create_profile_url_path


class User(AbstractUser):
    # FieldTracker doesn't work with abstract model classes
    tracker = FieldTracker(fields=["is_superuser", "password"])

    def save(self, *args, **kwargs) -> None:
        with self.tracker:
            if self.tracker.has_changed("password"):
                self.password_changed_date = timezone.now()
            super().save(*args, **kwargs)


post_save.connect(create_profile_url_path, sender=User)
