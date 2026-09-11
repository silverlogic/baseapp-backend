from typing import TYPE_CHECKING

from django.db import models
from django.utils.functional import cached_property

from .utils import _cache_object_type, get_obj_relay_id

if TYPE_CHECKING:
    from .object_types import DjangoObjectType


class RelayModel(models.Model):
    class Meta:
        abstract = True

    @cached_property
    def relay_id(self) -> str:
        return get_obj_relay_id(self)

    @classmethod
    def get_graphql_object_type(cls) -> type["DjangoObjectType"]:
        ot = _cache_object_type(cls)
        return ot
