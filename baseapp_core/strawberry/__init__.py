"""BaseApp's GraphQL layer on Strawberry / Strawberry Django."""

from .optimizer import install as _install_optimizer_overrides

_install_optimizer_overrides()

from .connections import CountedConnection  # noqa
from .mutations import (  # noqa
    ErrorType,
    IsAuthenticated,
    RelayMutationInput,
    RelayMutationPayload,
    relay_mutation,
)
from .registry import type_for_model, type_registry  # noqa
from .relay import Node, decode_global_id, model_from_info, node_field  # noqa
from .types import PublicIdOptimizerStore, django_type  # noqa
