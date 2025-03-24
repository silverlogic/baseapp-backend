from grapple.types.interfaces import PageInterface as GrapplePageInterface

from baseapp_wagtail.base.graphql.fields import GenericStreamFieldType


class PageInterface(GrapplePageInterface):
    body = GenericStreamFieldType(
        description="Body of the page", required=False
    )
