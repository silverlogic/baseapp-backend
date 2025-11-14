from django.contrib.gis import admin

from .models import GeoJSONFeature


@admin.register(GeoJSONFeature)
class GeoJSONFeatureAdmin(admin.GISModelAdmin):
    list_display = [
        "name",
        "user",
        "target_content_type",
        "target_object_id",
        "created",
        "modified",
    ]
    list_filter = ["target_content_type", "created", "modified"]
    search_fields = ["name", "user__email", "user__first_name", "user__last_name"]
    readonly_fields = ["created", "modified"]
    date_hierarchy = "created"

    fieldsets = (
        (None, {"fields": ("user", "name", "geometry")}),
        ("Linked Object", {"fields": ("target_content_type", "target_object_id")}),
        ("Timestamps", {"fields": ("created", "modified"), "classes": ("collapse",)}),
    )
