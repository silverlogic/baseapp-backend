import swapper
from django.contrib import admin

from baseapp_core.admin_helpers import ModelAdmin

File = swapper.load_model("baseapp_files", "File")
FileTarget = swapper.load_model("baseapp_files", "FileTarget")


@admin.register(File)
class FileAdmin(ModelAdmin):
    list_display = ("pk", "name", "file_content_type", "parent", "created_by", "created")
    list_filter = ("created", "upload_status", "file_content_type")
    search_fields = ("name", "description")
    raw_id_fields = ("created_by", "profile")


@admin.register(FileTarget)
class FileTargetAdmin(ModelAdmin):
    list_display = (
        "pk",
        "target",
        "is_files_enabled",
        "files_count",
    )
    list_filter = ("is_files_enabled",)
    search_fields = ("target_id",)
