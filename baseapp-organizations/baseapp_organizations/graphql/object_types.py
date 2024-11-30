import graphene
import swapper
from baseapp_auth.graphql.permissions import PermissionsInterface
from baseapp_core.graphql import DjangoObjectType, get_object_type_for_model
from graphene import relay

Organization = swapper.load_model("baseapp_organizations", "Organization")


class OrganizationInterface(relay.Node):
    organization = graphene.Field(get_object_type_for_model(Organization))


class AbstractOrganizationObjectType(object):
    class Meta:
        interfaces = (relay.Node,)
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
        interfaces = (relay.Node, PermissionsInterface)
        model = Organization
        fields = (
            "pk",
            "profile",
        )
