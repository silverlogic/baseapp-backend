import django_filters
import swapper
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.geos import Point, Polygon
from django.contrib.gis.measure import D
from django.core.exceptions import ValidationError
from django.db.models import Q, QuerySet
from django.utils.translation import gettext_lazy as _

from baseapp_core.hashids.utils import is_uuid4

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


def _resolve_target(value: str, field: str) -> tuple[ContentType, int]:
    """Resolve a relay global ID into `(content_type, object_id)` without a graphene context.

    Public IDs (UUID4) resolve through `DocumentId`; legacy base64 IDs are decoded with
    `graphql_relay.from_global_id` and mapped to a model via the graphene-django registry.
    Both graphene-adjacent imports are lazy so the FilterSet stays DRF-reusable.
    """
    if is_uuid4(value):
        from baseapp_core.models import DocumentId

        resolved = DocumentId.get_content_type_and_id_by_public_id(value)
        if resolved is None:
            raise ValidationError({field: [_("Target object does not exist.")]})
        return resolved

    try:
        from graphql_relay import from_global_id

        type_name, raw_pk = from_global_id(value)
        object_id = int(raw_pk)
    except Exception as exc:
        raise ValidationError({field: [_("Invalid relay global ID.")]}) from exc

    from graphene_django.registry import get_global_registry

    # Depends on graphene-django's private `_registry` dict (no public type-name lookup API).
    for model, object_type in get_global_registry()._registry.items():
        if object_type._meta.name == type_name:
            return ContentType.objects.get_for_model(model), object_id
    raise ValidationError({field: [_("Invalid relay global ID.")]})


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
    feature_type = django_filters.CharFilter(
        field_name="feature_type",
        lookup_expr="exact",
        help_text=_("Exact match on the feature's type label."),
    )
    target_object_id = django_filters.CharFilter(
        method="filter_target",
        help_text=_("Relay global ID of the object the features are attached to."),
    )

    class Meta:
        model = swapper.load_model("baseapp_geo", "GeoJSONFeature")
        fields = ["bbox", "near", "feature_type", "target_object_id"]

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
        """Filter features within `radiusMeters` of a `lng,lat` point.

        Uses ST_DWithin (`geometry__dwithin`): polygons match when their nearest
        edge is within the radius, not their centroid. Radius must satisfy
        0 < r <= MAX_NEAR_RADIUS_METERS.
        """
        lng, lat, radius = _parse_floats(value, 3, name)
        _validate_lon(lng, name)
        _validate_lat(lat, name)
        if not 0 < radius <= MAX_NEAR_RADIUS_METERS:
            raise ValidationError(
                {
                    name: [
                        _("Radius must be greater than 0 and at most %(max)d meters.")
                        % {"max": MAX_NEAR_RADIUS_METERS}
                    ]
                }
            )
        return queryset.filter(geometry__dwithin=(Point(lng, lat, srid=4326), D(m=radius)))

    def filter_target(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Filter features attached to the object identified by relay global ID `value`."""
        content_type, object_id = _resolve_target(value, name)
        return queryset.filter(
            target_document__content_type=content_type,
            target_document__object_id=object_id,
        )
