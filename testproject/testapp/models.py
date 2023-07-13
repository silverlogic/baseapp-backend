from django.utils import timezone
from django.db import models
from baseapp_core.models import CaseInsensitiveEmailField
from baseapp_auth.models import AbstractUser




from model_utils import FieldTracker


from django.contrib.auth.models import AbstractBaseUser


from importlib import import_module



class User(AbstractUser):
    # FieldTracker doesn't work with abstract model classes
    tracker = FieldTracker(fields=["is_superuser", "password"])


    def save(self, *args, **kwargs):
        with self.tracker:
            if self.tracker.has_changed("password"):
                self.password_changed_date = timezone.now()
            super().save(*args, **kwargs)
