from typing import Optional
from urllib.parse import urljoin, urlparse

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext as _
from grapple.models import GraphQLStreamfield
from wagtail.admin.panels import FieldPanel
from wagtail.api import APIField
from wagtail.models import Page, PageBase
from wagtail.search import index
from wagtail_headless_preview.models import HeadlessPreviewMixin

from baseapp_core.graphql.models import RelayModel

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

    url = headless_url

    def _has_no_domain(self, url: str) -> bool:
        parsed_url = urlparse(url)
        return not parsed_url.netloc

    @classmethod
    def get_front_url_path(cls, page) -> str:
        url_parts = page.get_url_parts()
        if not url_parts:
            return None
        _, _, page_path = url_parts
        return page_path

    class Meta:
        abstract = True


default_page_model_inheritances = []

if apps.is_installed("baseapp_pages"):
    from baseapp_pages.models import PageMixin

    default_page_model_inheritances.append(PageMixin)

default_page_model_inheritances.append(RelayModel)


class DefaultPageModel(
    HeadlessPageMixin, Page, *default_page_model_inheritances, metaclass=HeadlessPageBase
):
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

    graphql_fields = [
        GraphQLStreamfield("featured_image"),
    ]

    graphql_interfaces = []

    @property
    def pages_url_path(self):
        """
        baseapp_pages.models.PageMixin.url_path alternative.
        Defines a new property because wagtail pages already have a defined "url_path" property.
        """
        return self.url_paths.filter(
            Q(is_active=True), Q(language=self.locale.language_code) | Q(language__isnull=True)
        ).first()

    def update_url_path(self, path: str, language: Optional[str] = None, is_active: bool = True):
        """
        Overrides the baseapp_pages.models.PageMixin.update_url_path method.
        This is necessary in order to use the new "pages_url_path" property.
        """
        from baseapp_pages.utils.url_path_formatter import URLPathFormatter

        primary_path = self.pages_url_path or self.url_paths.first()
        if primary_path:
            primary_path.path = URLPathFormatter(path)()
            primary_path.language = language
            primary_path.is_active = is_active
            primary_path.save()
        else:
            self.create_url_path(path, language, is_active)

    def clean(self):
        super().clean()
        self._check_urlpath_is_unique()

    def _check_urlpath_is_unique(self):
        from baseapp_wagtail.base.urlpath.urlpath_sync import WagtailURLPathSync

        parent_path = self.get_front_url_path(self.get_parent()) if self.get_parent() else "/"
        path = urljoin(parent_path, self.slug)

        if WagtailURLPathSync(self).urlpath_exists(path):
            raise ValidationError(
                {
                    "slug": _(
                        "The url path generated from the slug is already in use by another page. Please try a different slug."
                    )
                }
            )

    class Meta:
        abstract = True


base_standard_page_model_inheritances = []

if apps.is_installed("baseapp_comments"):
    from baseapp_comments.models import CommentableModel

    base_standard_page_model_inheritances.append(CommentableModel)


base_standard_page_model_graphql_interfaces = []

if apps.is_installed("baseapp_comments"):
    base_standard_page_model_graphql_interfaces.append(
        "baseapp_wagtail.base.graphql.interfaces.WagtailCommentsInterface",
    )


class BaseStandardPage(DefaultPageModel, *base_standard_page_model_inheritances):
    body = PageBodyStreamField.create(
        StandardPageStreamBlock(required=False),
    )

    class Meta:
        verbose_name = _("Standard page")
        verbose_name_plural = _("Standard pages")
        abstract = True

    graphql_fields = [
        *DefaultPageModel.graphql_fields,
        GraphQLStreamfield("body"),
    ]

    graphql_interfaces = [
        *base_standard_page_model_graphql_interfaces,
    ]
