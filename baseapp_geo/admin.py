import swapper
from django.contrib import admin

from baseapp_core.admin_helpers import ModelAdmin

GeoJSONFeatureModel = swapper.load_model("baseapp_geo", "GeoJSONFeature")


@admin.register(GeoJSONFeatureModel)
class GeoJSONFeatureAdmin(ModelAdmin):
    list_display = ("name", "feature_type", "created")
