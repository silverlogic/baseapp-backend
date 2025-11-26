from django.contrib import admin
from django.contrib.contenttypes.admin import GenericStackedInline

from .models import File, FileTarget


class FileInlineAdmin(GenericStackedInline):
    model = File
    ct_field = "parent_content_type"
    ct_fk_field = "parent_object_id"
    raw_id_fields = ("created_by",)


@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    list_display = ("pk", "name", "file_content_type", "parent", "created_by", "created")
    search_fields = ("name",)
    raw_id_fields = ("created_by",)


@admin.register(FileTarget)
class FileTargetAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "target_content_type",
        "target_object_id",
        "is_files_enabled",
        "files_count",
    )
    list_filter = ("is_files_enabled", "target_content_type")
    search_fields = ("target_object_id",)
