import swapper

from baseapp_auth.graphql.permissions import PermissionsInterface
from baseapp_core.graphql import DjangoObjectType
from baseapp_core.graphql import Node as RelayNode

Organization = swapper.load_model("baseapp_organizations", "Organization")


class AbstractOrganizationObjectType(object):
    class Meta:
        interfaces = (RelayNode,)
        model = Organization
        fields = (
            "pk",
            "profile",
        )

    @classmethod
    def get_node(self, info, id):
        if not info.context.user.has_perm("baseapp_organizations.view_organization"):
            return None
        node = super().get_node(info, id)
        return node


class OrganizationObjectType(AbstractOrganizationObjectType, DjangoObjectType):
    class Meta:
        interfaces = (RelayNode, PermissionsInterface)
        model = Organization
        fields = (
            "pk",
            "profile",
        )
