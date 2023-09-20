import swapper
from django.contrib import admin

File = swapper.load_model("baseapp_files", "File")
FileTarget = swapper.load_model("baseapp_files", "FileTarget")


@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    list_display = ("pk", "name", "file_content_type", "parent", "created_by", "created")
    search_fields = ("name",)
    raw_id_fields = ("created_by",)


@admin.register(FileTarget)
class FileTargetAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "target",
        "is_files_enabled",
        "files_count",
    )
    list_filter = ("is_files_enabled",)
    search_fields = ("target_id",)
