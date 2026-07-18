import django_filters
import swapper
from django.contrib.gis.geos import Point, Polygon
from django.contrib.gis.measure import D
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _

MAX_NEAR_RADIUS_METERS = 100_000


def _parse_floats(value: str, count: int) -> list[float]:
    """Parse a comma-separated string into exactly `count` floats."""
    return [float(part) for part in value.split(",", count - 1)]


class GeoJSONFeatureFilter(django_filters.FilterSet):
    bbox = django_filters.CharFilter(
        method="filter_bbox",
        help_text=_("Bounding box as minLon,minLat,maxLon,maxLat (WGS 84)."),
    )
    near = django_filters.CharFilter(
        method="filter_near",
        help_text=_(
            "Proximity as lng,lat,radiusMeters. Uses ST_DWithin: polygons match "
            "when their nearest edge is within the radius, not their centroid."
        ),
    )

    class Meta:
        model = swapper.load_model("baseapp_geo", "GeoJSONFeature")
        fields = ["bbox", "near"]

    def filter_bbox(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        west, south, east, north = _parse_floats(value, 4)
        return queryset.filter(geometry__intersects=Polygon.from_bbox((west, south, east, north)))

    def filter_near(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        lng, lat, radius = _parse_floats(value, 3)
        return queryset.filter(geometry__dwithin=(Point(lng, lat, srid=4326), D(m=radius)))
