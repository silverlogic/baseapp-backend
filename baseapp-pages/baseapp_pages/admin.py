import swapper
from django.contrib import admin
from django.contrib.contenttypes.admin import GenericStackedInline, GenericTabularInline
from translated_fields import TranslatedFieldAdmin

from baseapp_pages.models import Metadata, URLPath

Page = swapper.load_model("baseapp_pages", "Page")


class URLPathAdminInline(GenericTabularInline):
    model = URLPath
    extra = 0
    ct_field = "target_content_type"
    ct_fk_field = "target_object_id"


@admin.register(URLPath)
class URLPathAdmin(admin.ModelAdmin):
    search_fields = ("path",)
    list_display = ("id", "path", "language", "is_active", "target", "created")
    list_filter = ("target_content_type", "language", "is_active")


class MetadataAdminInline(GenericStackedInline):
    model = Metadata
    extra = 0
    ct_field = "target_content_type"
    ct_fk_field = "target_object_id"


@admin.register(Page)
class PageAdmin(TranslatedFieldAdmin, admin.ModelAdmin):
    search_fields = ("title", "body")
    raw_id_fields = ("user",)
    list_display = ("id", "title", "created", "modified")
    inlines = [URLPathAdminInline, MetadataAdminInline]


@admin.register(Metadata)
class MetadataAdmin(admin.ModelAdmin):
    search_fields = ("meta_title", "meta_description")
    list_display = ("target", "meta_title", "language", "created", "modified")
    list_filter = ("target_content_type", "language")
