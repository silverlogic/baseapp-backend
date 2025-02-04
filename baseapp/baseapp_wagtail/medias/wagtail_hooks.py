from typing import List

from django.utils.html import escape
from wagtail import hooks
from wagtail.documents.rich_text import DocumentLinkHandler


@hooks.register("register_rich_text_features", order=1)
def register_document_feature(features):
    features.register_link_type(CustomDocumentLinkHandler)


class CustomDocumentLinkHandler(DocumentLinkHandler):
    @classmethod
    def expand_db_attributes_many(cls, attrs_list: List[dict]) -> List[str]:
        return [
            '<a href="%s" target="_blank">' % escape(doc.url) if doc else "<a>"
            for doc in cls.get_many(attrs_list)
        ]
