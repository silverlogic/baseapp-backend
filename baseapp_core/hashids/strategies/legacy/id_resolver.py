from typing import TYPE_CHECKING, Any

from baseapp_core.hashids.strategies.interfaces import IdResolverStrategy

if TYPE_CHECKING:
    from django.db.models import Model


class LegacyIdResolverStrategy(IdResolverStrategy):
    def get_id_from_instance(self, instance) -> Any:
        return instance.pk

    def resolve_id(self, id, *, model_cls=None, **kwargs) -> "Model":
        if not model_cls:
            raise ValueError("model_cls is required")
        return model_cls.objects.get(pk=id)
