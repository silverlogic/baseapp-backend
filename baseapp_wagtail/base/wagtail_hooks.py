from django.utils.html import escape
from wagtail import hooks
from wagtail.rich_text import LinkHandler

from baseapp_wagtail.base.urlpath.urlpath_sync import WagtailURLPathSync


@hooks.register("register_rich_text_features")
def register_core_features(features):
    features.default_features.append("blockquote")
    features.register_link_type(ExternalLinkHandler)
    features.register_link_type(EmailLinkHandler)


@hooks.register("register_schema_query")
def register_schema_query(query_mixins):
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


@hooks.register("after_create_page")
def create_urlpath_for_page(request, page):
    WagtailURLPathSync(page).create_urlpath()


@hooks.register("after_publish_page")
def update_urlpath_on_publish(request, page):
    WagtailURLPathSync(page).update_urlpath()


@hooks.register("after_unpublish_page")
def deactivate_urlpath_on_unpublish(request, page):
    WagtailURLPathSync(page).deactivate_urlpath()


@hooks.register("after_delete_page")
def delete_urlpath_on_delete(request, page):
    WagtailURLPathSync(page).delete_urlpath()
