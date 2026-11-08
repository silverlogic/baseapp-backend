from dataclasses import dataclass, field
from typing import Any, Literal

from django.db.models import Model
from strawberry.types.lazy_type import LazyType


@dataclass
class TypeEntry:
    strawberry_type: type
    filterset_class: Any = None
    relations: Literal["__all__"] | tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()


class StrawberryTypeRegistry:
    """Model -> Strawberry type map. The last registration wins, so projects can override types."""

    def __init__(self) -> None:
        self._entries: dict[type[Model], TypeEntry] = {}

    def register(self, model: type[Model], strawberry_type: type, **options: Any) -> None:
        self._entries[model] = TypeEntry(strawberry_type, **options)

    def get_entry(self, model: type[Model]) -> TypeEntry | None:
        for candidate in (model, model._meta.concrete_model, *model.__mro__):
            if candidate in self._entries:
                return self._entries[candidate]
        return None

    def get_type_for_model(self, model: type[Model]) -> type | None:
        entry = self.get_entry(model)
        return entry.strawberry_type if entry else None

    def entries(self) -> dict[type[Model], TypeEntry]:
        return dict(self._entries)


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
