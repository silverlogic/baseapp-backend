import swapper

from baseapp_core.graphql import Node, get_object_type_for_model

Organization = swapper.load_model("baseapp_organizations", "Organization")


class OrganizationsQueries:
    organization = Node.Field(get_object_type_for_model(Organization))
