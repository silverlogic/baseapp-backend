import swapper
from django.contrib import admin

from baseapp_core.admin_helpers import ModelAdmin
from baseapp_core.plugins import apply_if_installed

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
    autocomplete_fields = (
        "parent",
        "created_by",
        *apply_if_installed("baseapp_profiles", ["profile"]),
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
