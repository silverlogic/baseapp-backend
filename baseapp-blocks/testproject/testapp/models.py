from baseapp_auth.models import AbstractUser
from django.utils import timezone
from model_utils import FieldTracker

from baseapp_blocks.models import BlockableModel


class User(AbstractUser, BlockableModel):
    # FieldTracker doesn't work with abstract model classes
    tracker = FieldTracker(fields=["is_superuser", "password"])

    def save(self, *args, **kwargs):
        with self.tracker:
            if self.tracker.has_changed("password"):
                self.password_changed_date = timezone.now()
            super().save(*args, **kwargs)

    def has_permission(self, permission, obj=None):
        if permission == "block.as_actor":
            return self == obj
        if permission == "block.add_block":
            return True
        if permission == "block.delete_block":
            return True
