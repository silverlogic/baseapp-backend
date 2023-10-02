from django.db import models
from django.utils.functional import cached_property

from .utils import get_obj_relay_id


class RelayModel(models.Model):
    class Meta:
        abstract = True

    @cached_property
    def relay_id(self):
        return get_obj_relay_id(self)
