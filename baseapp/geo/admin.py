import swapper
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from baseapp_core.admin_helpers import ModelAdmin
from baseapp_core.plugins.helpers import apply_if_installed

GeoJSONFeatureModel = swapper.load_model("baseapp_geo", "GeoJSONFeature")


@admin.register(GeoJSONFeatureModel)
class GeoJSONFeatureAdmin(ModelAdmin):
    list_display = ("name", "feature_type", "geometry_type", "target", "created_by", "created")
    list_filter = ("feature_type",)
    search_fields = ("name", "description")
    raw_id_fields = ("target_document",)
    # `profile` only exists when baseapp_profiles is installed.
    autocomplete_fields = ("created_by", *apply_if_installed("baseapp_profiles", ["profile"]))

    @admin.display(description=_("geometry type"))
    def geometry_type(self, obj) -> str:
        return obj.geometry.geom_type

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("target_document__content_type", "created_by")
            .prefetch_related("target_document__content_object")
        )
