from graphene_django import DjangoObjectType
from grapple.types.interfaces import get_page_interface
from wagtail.models import Page as WagtailPage

# from baseapp_comments.graphql.object_types import CommentsInterface


# TODO: (wagtail) Move the list of interfaces to inside of the model using graphql_interfaces.
class Page(DjangoObjectType):
    class Meta:
        model = WagtailPage
        # interfaces = (get_page_interface(), CommentsInterface,)
        # TODO: (wagtail) test CommentsInterface (I think we need to use relay.Node as well).
        interfaces = (get_page_interface(),)
