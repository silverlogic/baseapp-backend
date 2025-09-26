from django.utils.html import escape
from wagtail import hooks
from wagtail.rich_text import LinkHandler

from baseapp_wagtail.base.urlpath.urlpath_sync import WagtailURLPathSync
from baseapp_wagtail.base.metadata.metadata_sync import WagtailMetadataSync


@hooks.register("register_schema_query")
def register_schema_query(query_mixins):
    for query_mixin in query_mixins:
        # TODO: (wagtail) this is conflicting with the search query from BA.
        if query_mixin.__module__ == "grapple.types.search":
            query_mixins.remove(query_mixin)


@hooks.register("after_publish_page")
def save_urlpath_draft_on_schedule_publish(request, page):
    if page.scheduled_revision:
        WagtailURLPathSync(page.scheduled_revision.as_object()).create_or_update_urlpath_draft()


@hooks.register("after_publish_page")
def sync_metadata_on_publish(request, page):
    WagtailMetadataSync(page).create_or_update_metadata()


@hooks.register("register_rich_text_features")
def register_core_features(features):
    features.default_features.append("blockquote")
    features.register_link_type(ExternalLinkHandler)
    features.register_link_type(EmailLinkHandler)


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
