from django.contrib import admin
from django.contrib.contenttypes.admin import GenericStackedInline

from .models import File


class FileInlineAdmin(GenericStackedInline):
    model = File
    ct_field = "parent_content_type"
    ct_fk_field = "parent_object_id"
    raw_id_fields = ("created_by",)


@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    list_display = ("pk", "name", "content_type", "parent", "created_by", "created")
    search_fields = ("name",)
    raw_id_fields = ("created_by",)
