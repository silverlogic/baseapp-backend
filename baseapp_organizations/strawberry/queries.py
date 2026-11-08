import strawberry

from baseapp_core.strawberry.relay import typed_node_field

from .types import OrganizationLazyType


@strawberry.type
class OrganizationsQueries:
    organization = typed_node_field(OrganizationLazyType)
