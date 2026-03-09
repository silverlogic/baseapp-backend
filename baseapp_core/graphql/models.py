from django.db import models
from django.utils.functional import cached_property

from baseapp_core.models import DocumentIdMixin

from .utils import _cache_object_type, get_obj_relay_id


class RelayModel(DocumentIdMixin, models.Model):
    class Meta:
        abstract = True

    @cached_property
    def relay_id(self):
        return get_obj_relay_id(self)

    @classmethod
    def get_graphql_object_type(cls):
        ot = _cache_object_type(cls)
        return ot
