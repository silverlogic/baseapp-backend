from django.utils.html import escape
from wagtail import hooks
from wagtail.rich_text import LinkHandler


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
