from dataclasses import dataclass, field
from typing import Any

from django.db.models import Model
from strawberry.types.lazy_type import LazyType


class StrawberryTypeRegistry:
    """Model -> Strawberry type map. The last registration wins, so projects can override types."""

    def __init__(self) -> None:
        self._types: dict[type[Model], type] = {}

    def register(self, model: type[Model], strawberry_type: type) -> None:
        self._types[model] = strawberry_type

    def get_type_for_model(self, model: type[Model]) -> type | None:
        for candidate in (model, model._meta.concrete_model, *model.__mro__):
            if candidate in self._types:
                return self._types[candidate]
        return None


type_registry = StrawberryTypeRegistry()


@dataclass(frozen=True)
class ModelLazyType(LazyType):
    """A LazyType resolved through the registry at schema build time, not by module path."""

    model: Any = field(default=None, compare=False)

    def resolve_type(self) -> type[Any]:
        strawberry_type = type_registry.get_type_for_model(self.model)
        if strawberry_type is None:
            raise LookupError(f"No Strawberry type registered for {self.model.__name__}")
        return strawberry_type


def type_for_model(model: type[Model]) -> Any:
    """Reference a model's GraphQL type without importing it, honouring project overrides."""
    return ModelLazyType(type_name=model.__name__, module=__name__, model=model)
