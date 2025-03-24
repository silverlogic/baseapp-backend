from graphene_django import DjangoObjectType
from grapple.types.interfaces import get_page_interface
from wagtail.models import Page as WagtailPage

from baseapp_comments.graphql.object_types import CommentsInterface


class Page(DjangoObjectType):
    class Meta:
        model = WagtailPage
        interfaces = (get_page_interface(), CommentsInterface,)
