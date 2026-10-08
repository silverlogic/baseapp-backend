import logging

import swapper
from django.core.exceptions import ValidationError
from django.db.models import Expression, F, QuerySet
from django.http import Http404, HttpResponse
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from baseapp.geo.graphql.filters import GeoJSONFeatureFilter
from baseapp.geo.tiles import Tile, build_clusters_tile, build_features_tile

from .permissions import CanViewGeoJSONFeatures

logger = logging.getLogger(__name__)

MVT_CONTENT_TYPE = "application/vnd.mapbox-vector-tile"


class GeoJSONFeatureTileView(APIView):
    """Mapbox Vector Tile of GeoJSON features: `GET .../geo/tiles/{z}/{x}/{y}.mvt`.

    From `cluster_max_zoom` up, the tile's `features` layer holds every feature (with `id`,
    `feature_type` and `get_feature_properties()` as attributes). Below it, the `clusters`
    layer aggregates them into grid cells with a `point_count`. Query parameters are the same
    filters as the `geoFeatures` GraphQL connection (e.g. `feature_type`, `target_object_id`).

    Extension points for projects: `get_queryset`, `filter_queryset` and
    `get_feature_properties` (e.g. to add attributes of the target object).
    """

    permission_classes = [CanViewGeoJSONFeatures]
    filterset_class = GeoJSONFeatureFilter

    features_layer = "features"
    clusters_layer = "clusters"
    cluster_max_zoom = 13
    cluster_grid_size = 16
    # Short enough for new features to show up soon, long enough for a CDN to absorb map pans.
    cache_max_age = 300

    def get_queryset(self) -> QuerySet:
        return swapper.load_model("baseapp_geo", "GeoJSONFeature").objects.all()

    def filter_queryset(self, queryset: QuerySet) -> QuerySet:
        """Apply `filterset_class` to the query parameters; raises ValidationError on bad input."""
        filterset = self.filterset_class(self.request.query_params, queryset=queryset)
        if not filterset.is_valid():
            raise ValidationError(filterset.errors)
        return filterset.qs

    def get_feature_properties(self) -> dict[str, Expression]:
        """MVT attributes of each feature: name → ORM expression (string, number or boolean)."""
        return {"id": F("pk"), "feature_type": F("feature_type")}

    def get(self, request: Request, z: int, x: int, y: int) -> HttpResponse:
        tile = Tile(z, x, y)
        if not tile.is_valid:
            raise Http404(_("Tile out of range."))

        try:
            queryset = self.filter_queryset(self.get_queryset())
            prefilter = tile.prefilter_polygon()
            if prefilter is not None:
                queryset = queryset.filter(geometry__intersects=prefilter)

            if z < self.cluster_max_zoom:
                content = build_clusters_tile(
                    tile, queryset, grid_size=self.cluster_grid_size, layer=self.clusters_layer
                )
            else:
                content = build_features_tile(
                    tile,
                    queryset,
                    properties=self.get_feature_properties(),
                    layer=self.features_layer,
                )
        except ValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "error_dict") else {"detail": exc.messages}
            return Response(detail, status=status.HTTP_400_BAD_REQUEST)

        response = HttpResponse(
            content,
            content_type=MVT_CONTENT_TYPE,
            status=status.HTTP_200_OK if content else status.HTTP_204_NO_CONTENT,
        )
        response["Cache-Control"] = f"public, max-age={self.cache_max_age}"
        return response
