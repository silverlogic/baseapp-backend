from django.db import models

from .utils import get_obj_relay_id


class RelayModel(models.Model):
    class Meta:
        abstract = True

    @property
    def relay_id(self):
        return get_obj_relay_id(self)
