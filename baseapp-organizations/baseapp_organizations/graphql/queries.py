import swapper
from baseapp_core.graphql import Node

from baseapp_organizations.graphql.object_types import OrganizationObjectType

Organization = swapper.load_model("baseapp_organizations", "Organization")


class OrganizationsQueries:
    organization = Node.Field(OrganizationObjectType)
