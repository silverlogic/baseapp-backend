import swapper
from django.apps import apps
from django.contrib import admin

from baseapp_core.admin_helpers import ModelAdmin

File = swapper.load_model("baseapp_files", "File")
FileTarget = swapper.load_model("baseapp_files", "FileTarget")


@admin.register(File)
class FileAdmin(ModelAdmin):
    list_display = ("pk", "name", "file_content_type", "parent", "created_by", "created")
    list_filter = ("created", "upload_status", "file_content_type")
    list_select_related = ("parent__content_type", "created_by")
    search_fields = ("name", "description")
    # Autocomplete instead of <select>: `parent` points at the global DocumentId registry,
    # and rendering every row as an option made the change form unusable. `profile` (the
    # profile that created the file) only exists when baseapp_profiles is installed.
    autocomplete_fields = ("parent", "created_by") + (
        ("profile",) if apps.is_installed("baseapp_profiles") else ()
    )


@admin.register(FileTarget)
class FileTargetAdmin(ModelAdmin):
    list_display = (
        "pk",
        "target",
        "is_files_enabled",
        "files_count",
    )
    list_filter = ("is_files_enabled",)
    list_select_related = ("target__content_type",)
    search_fields = ("target_id",)
    autocomplete_fields = ("target",)
