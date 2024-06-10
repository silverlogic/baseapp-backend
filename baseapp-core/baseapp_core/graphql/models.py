from django.db import models
from django.utils.functional import cached_property

from .utils import _cache_object_type, get_obj_relay_id


class RelayModel(models.Model):
    class Meta:
        abstract = True

    @cached_property
    def relay_id(self):
        return get_obj_relay_id(self)

    @property
    def GraphQLObjectType(self):
        ot = _cache_object_type(self)
        return ot
