from django.db import models
from django.utils.functional import cached_property

from .utils import get_obj_relay_id, _cache_object_type


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
