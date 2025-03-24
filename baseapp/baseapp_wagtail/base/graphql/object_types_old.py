from __future__ import unicode_literals
import graphene
from graphene_django import DjangoObjectType

from . import fields  # noqa
# TODO: remove test ref.
from testproject.base.models import StandardPage


class MetaFields(graphene.ObjectType):
    html_url = graphene.String()
    slug = graphene.String()
    show_in_menus = graphene.Boolean()
    seo_title = graphene.String()
    search_description = graphene.String()
    first_published_at = graphene.DateTime()
    alias_of = graphene.String()
    parent = graphene.String()
    locale = graphene.String()


class BaseWagtailPageObjectType:
    meta = graphene.Field(MetaFields)

    class Meta:
        model = StandardPage
        only_fields = ["id", "title", "meta", "body"]

    def resolve_meta(self, info):
        return {
            "html_url": self.html_url,
            "slug": self.slug,
            "show_in_menus": self.show_in_menus,
            "seo_title": self.seo_title,
            "search_description": self.search_description,
            "first_published_at": self.first_published_at,
            "alias_of": self.alias_of,
            "parent": self.parent,
            "locale": self.locale,
        }


class WagtailPageObjectType(BaseWagtailPageObjectType, DjangoObjectType):
    class Meta(BaseWagtailPageObjectType.Meta):
        pass
