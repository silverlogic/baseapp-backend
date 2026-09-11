import swapper
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from baseapp_core.admin_helpers import ModelAdmin

GeoJSONFeatureModel = swapper.load_model("baseapp_geo", "GeoJSONFeature")


@admin.register(GeoJSONFeatureModel)
class GeoJSONFeatureAdmin(ModelAdmin):
    list_display = ("name", "feature_type", "geometry_type", "target", "created")
    list_filter = ("feature_type",)
    search_fields = ("name", "description")
    raw_id_fields = ("target_document",)

    @admin.display(description=_("geometry type"))
    def geometry_type(self, obj) -> str:
        return obj.geometry.geom_type

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("target_document__content_type")
            .prefetch_related("target_document__content_object")
        )
