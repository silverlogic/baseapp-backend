from urllib.parse import urlparse

from django.conf import settings
from django.utils.translation import gettext as _
from wagtail.admin.panels import FieldPanel
from wagtail.api import APIField
from wagtail.models import Page, PageBase
from wagtail.search import index
from wagtail_headless_preview.models import HeadlessPreviewMixin

from .stream_fields import (
    FeaturedImageStreamField,
    PageBodyStreamField,
    StandardPageStreamBlock,
)


class HeadlessPageBase(PageBase):
    def __init__(cls, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Guarantee that the jinja2 template will be empty.
        cls.template = "pages/empty.html"


class HeadlessPageMixin(HeadlessPreviewMixin):
    @property
    def headless_url(self, request=None, current_site=None):
        url = self.get_url(request, current_site)
        if (root_url := settings.FRONT_HEADLESS_URL) and url and self._has_no_domain(url):
            return root_url + url
        return url

    # This is a workaround to fix the headless_url property for "View live" buttons.
    url = headless_url

    def _has_no_domain(self, url: str) -> bool:
        parsed_url = urlparse(url)
        return not parsed_url.netloc

    class Meta:
        abstract = True


class DefaultPageModel(HeadlessPageMixin, Page, metaclass=HeadlessPageBase):
    featured_image = FeaturedImageStreamField.create()
    body = None

    content_panels = Page.content_panels + [
        FieldPanel("featured_image", classname="collapsed"),
        FieldPanel("body"),
    ]

    api_fields = [
        APIField("featured_image"),
        APIField("body"),
    ]

    search_fields = Page.search_fields + [
        index.SearchField("body"),
        index.AutocompleteField("body"),
    ]

    class Meta:
        abstract = True


class BaseStandardPage(DefaultPageModel):
    body = PageBodyStreamField.create(
        StandardPageStreamBlock(required=False),
    )

    class Meta:
        verbose_name = _("Standard page")
        verbose_name_plural = _("Standard pages")
        abstract = True
