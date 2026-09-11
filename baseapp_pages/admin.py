from typing import TYPE_CHECKING

import swapper
from django.contrib import admin
from django.contrib.contenttypes.admin import GenericStackedInline, GenericTabularInline
from translated_fields import TranslatedFieldAdmin

from baseapp_core.admin_helpers import ModelAdmin, StackedInline, TabularInline
from baseapp_pages.models import Metadata, URLPath

if TYPE_CHECKING:
    from django.db.models import Model

Page = swapper.load_model("baseapp_pages", "Page")


class URLPathAdminInline(GenericTabularInline, TabularInline):
    model = URLPath
    extra = 0
    ct_field = "target_content_type"
    ct_fk_field = "target_object_id"


@admin.register(URLPath)
class URLPathAdmin(ModelAdmin):
    search_fields = ("path",)
    list_display = ("id", "path", "language", "is_active", "view_target", "created")
    list_filter = ("target_content_type", "language", "is_active")

    @admin.display(description="target")
    def view_target(self, obj) -> "Model | str":
        try:
            return obj.target if obj.target else "-"
        except AttributeError:
            return "-"


@admin.register(Metadata)
class MetadataAdmin(ModelAdmin):
    search_fields = ("meta_title", "meta_description")
    list_display = ("target", "meta_title", "language", "created", "modified")
    list_filter = ("target_content_type", "language")


class MetadataAdminInline(GenericStackedInline, StackedInline):
    model = Metadata
    extra = 0
    ct_field = "target_content_type"
    ct_fk_field = "target_object_id"


@admin.register(Page)
class PageAdmin(TranslatedFieldAdmin, ModelAdmin):
    search_fields = ("title", "body")
    raw_id_fields = ("user",)
    list_display = ("id", "title", "created", "modified")
    list_filter = ("status",)
    inlines = [URLPathAdminInline, MetadataAdminInline]
