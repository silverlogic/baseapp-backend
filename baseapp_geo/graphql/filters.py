import django_filters
import swapper
from django.contrib.gis.geos import Point, Polygon
from django.contrib.gis.measure import D
from django.core.exceptions import ValidationError
from django.db.models import Q, QuerySet
from django.utils.translation import gettext_lazy as _

MAX_NEAR_RADIUS_METERS = 100_000


def _parse_floats(value: str, arity: int, field: str) -> list[float]:
    """Parse a comma-separated string into exactly `arity` floats or raise ValidationError."""
    parts = value.split(",")
    if len(parts) != arity:
        raise ValidationError(
            {field: [_("Expected %(arity)d comma-separated numbers.") % {"arity": arity}]}
        )
    try:
        return [float(part) for part in parts]
    except ValueError as exc:
        raise ValidationError({field: [_("All values must be valid numbers.")]}) from exc


def _validate_lon(value: float, field: str) -> None:
    """Raise ValidationError unless `value` is a valid WGS 84 longitude."""
    if not -180 <= value <= 180:
        raise ValidationError({field: [_("Longitude must be between -180 and 180.")]})


def _validate_lat(value: float, field: str) -> None:
    """Raise ValidationError unless `value` is a valid WGS 84 latitude."""
    if not -90 <= value <= 90:
        raise ValidationError({field: [_("Latitude must be between -90 and 90.")]})


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
        west, south, east, north = _parse_floats(value, 4, name)
        _validate_lon(west, name)
        _validate_lon(east, name)
        _validate_lat(south, name)
        _validate_lat(north, name)
        if south > north:
            raise ValidationError({name: [_("bbox south must not be greater than north.")]})
        if west > east:
            # Antimeridian-crossing bbox (RFC 7946 §5.2): split into two OR-ed boxes.
            return queryset.filter(
                Q(geometry__intersects=Polygon.from_bbox((west, south, 180.0, north)))
                | Q(geometry__intersects=Polygon.from_bbox((-180.0, south, east, north)))
            )
        return queryset.filter(geometry__intersects=Polygon.from_bbox((west, south, east, north)))

    def filter_near(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        lng, lat, radius = _parse_floats(value, 3, name)
        return queryset.filter(geometry__dwithin=(Point(lng, lat, srid=4326), D(m=radius)))
