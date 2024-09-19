from urllib.parse import urlparse

from django.conf import settings
from django.utils.translation import gettext as _
from wagtail.admin.panels import FieldPanel
from wagtail.api import APIField
from wagtail.fields import StreamField
from wagtail.models import Page
from wagtail.search import index
from wagtail_headless_preview.models import HeadlessPreviewMixin

from .stream_fields import (
    FeaturedImageStreamBlock,
    PageBodyStreamField,
    StandardPageStreamBlock,
)


class HeadlessPageMixin(HeadlessPreviewMixin):
    @property
    def headless_url(self, request=None, current_site=None):
        url = self.get_url(request, current_site)
        if self._has_no_domain(url):
            # TODO: adjust method to only work with headless mode.
            root_url = settings.FRONT_HEADLESS_URL
            return root_url + url
        return url

    # This is a workaround to fix the headless_url property for "View live" buttons.
    url = headless_url

    def _has_no_domain(self, url: str) -> bool:
        parsed_url = urlparse(url)
        return not parsed_url.netloc

    class Meta:
        abstract = True


class DefaultPageModel(HeadlessPageMixin, Page):
    featured_image = StreamField(
        FeaturedImageStreamBlock(max_num=1),
        verbose_name="Featured Image",
        null=True,
        blank=False,
        use_json_field=True,
    )
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


class StandardPage(DefaultPageModel):
    body = PageBodyStreamField.create(
        StandardPageStreamBlock(required=False),
    )

    class Meta:
        verbose_name = _("Standard page")
        verbose_name_plural = _("Standard pages")


# TODO: make classes above swappable.
