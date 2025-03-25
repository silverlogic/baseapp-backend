from django.utils.html import escape
from grapple.registry import registry
from wagtail import hooks
from wagtail.models import Page as WagtailPage
from wagtail.rich_text import LinkHandler

from .graphql.object_types import Page


@hooks.register("register_rich_text_features")
def register_core_features(features):
    features.default_features.append("blockquote")
    features.register_link_type(ExternalLinkHandler)
    features.register_link_type(EmailLinkHandler)


@hooks.register("register_schema_query")
def register_schema_query(query_mixins):
    registry.pages[type(WagtailPage)] = Page
    for query_mixin in query_mixins:
        # TODO: (wagtail) this is conflicting with the search query from BA.
        if query_mixin.__module__ == "grapple.types.search":
            query_mixins.remove(query_mixin)


class ExternalLinkHandler(LinkHandler):
    identifier = "external"

    @classmethod
    def expand_db_attributes(cls, attrs):
        href = attrs["href"]
        return '<a href="%s" target="_blank" rel="noopener noreferrer">' % escape(href)


class EmailLinkHandler(LinkHandler):
    identifier = "email"

    @classmethod
    def expand_db_attributes(cls, attrs):
        href = attrs["href"]
        return '<a href="%s" class="notranslate">' % escape(href)
