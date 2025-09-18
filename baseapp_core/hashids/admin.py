from django.contrib import admin

from .models import PublicIdMapping


@admin.register(PublicIdMapping)
class PublicIdMappingAdmin(admin.ModelAdmin):
    list_display = ("public_id", "content_type", "object_id")
    search_fields = ("public_id", "content_type__model", "object_id")
    list_filter = ("content_type",)
    raw_id_fields = ("content_type",)
    date_hierarchy = "created"
    ordering = ("-created",)
