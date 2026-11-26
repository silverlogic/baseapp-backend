from typing import Any, Optional, Type

from baseapp_core.hashids.strategies.interfaces.id_resolver import IdResolverStrategy


class DRFResolverStrategy:
    class NoInstanceFound(Exception):
        """The id points at a row of a different model than the one expected."""

        def __init__(self, public_id: Any) -> None:
            super().__init__(f"No instance found for public id: {public_id}")

    def __init__(self, id_resolver: IdResolverStrategy) -> None:
        self.id_resolver = id_resolver

    def resolve_public_id_to_pk(
        self, public_id: Any, expected_model: Optional[Type[Any]] = None
    ) -> int | str | None:
        """Return the pk the id maps to, or None when nothing is mapped to it.

        Raise `NoInstanceFound` when `expected_model` is given and the id belongs to another model.
        """
        raise NotImplementedError
