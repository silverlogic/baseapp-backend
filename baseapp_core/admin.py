from django.contrib import admin

from baseapp_core.models import DocumentId


@admin.register(DocumentId)
class DocumentIdAdmin(admin.ModelAdmin):
    list_display = ("public_id", "content_type", "object_id")
    search_fields = ("public_id", "content_type__model", "object_id")
    list_filter = ("content_type",)
    raw_id_fields = ("content_type",)
    list_select_related = ("content_type",)
    date_hierarchy = "created"
    ordering = ("-created",)

    readonly_fields = ("public_id", "content_type", "object_id", "created")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
