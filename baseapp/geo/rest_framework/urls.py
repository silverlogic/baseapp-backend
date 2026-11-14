from django.urls import path

from .views import GeoJSONFeatureTileView

urlpatterns = [
    path(
        "geo/tiles/<int:z>/<int:x>/<int:y>.mvt",
        GeoJSONFeatureTileView.as_view(),
        name="geo-feature-tiles",
    ),
]
