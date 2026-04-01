from django.db.models.signals import post_save
from django.utils import timezone
from model_utils import FieldTracker

from baseapp_auth.models import AbstractUser
from baseapp_core.graphql.models import RelayModel
from baseapp_profiles.models import ProfilableModel
from baseapp_profiles.signals import create_profile_url_path
from baseapp_ratings.models import RatableModel


class User(AbstractUser, RelayModel, RatableModel, ProfilableModel):
    profile_name_sql = "NEW.first_name || ' ' || NEW.last_name"
    profile_owner_sql = "NEW.id"

    # FieldTracker doesn't work with abstract model classes
    tracker = FieldTracker(fields=["is_superuser", "password"])

    def save(self, *args, **kwargs):
        with self.tracker:
            if self.tracker.has_changed("password"):
                self.password_changed_date = timezone.now()
            super().save(*args, **kwargs)


post_save.connect(create_profile_url_path, sender=User)
