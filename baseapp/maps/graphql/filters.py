import django_filters
from django.contrib.gis.geos import Polygon

from ..models import GeoJSONFeature


class GeoJSONFeatureFilter(django_filters.FilterSet):
    """
    Filter for GeoJSON features with bounding box support.

    Example bbox format: "minLon,minLat,maxLon,maxLat" (e.g., "-180,-90,180,90")
    """

    q = django_filters.CharFilter(method="filter_q", label="Search")
    bbox = django_filters.CharFilter(method="filter_bbox", label="Bounding Box")

    order_by = django_filters.OrderingFilter(
        fields=(
            ("created", "created"),
            ("modified", "modified"),
            ("name", "name"),
        )
    )

    class Meta:
        model = GeoJSONFeature
        fields = ["q", "bbox", "order_by", "target_content_type"]

    def filter_q(self, queryset, name, value):
        """Filter by name search."""
        return queryset.filter(name__icontains=value)

    def filter_bbox(self, queryset, name, value):
        """
        Filter features that intersect with the given bounding box.

        Expected format: "minLon,minLat,maxLon,maxLat"
        Example: "-122.5,37.7,-122.3,37.9"
        """
        if not value:
            return queryset

        try:
            # Parse bbox string: "minLon,minLat,maxLon,maxLat"
            coords = [float(coord.strip()) for coord in value.split(",")]

            if len(coords) != 4:
                return queryset

            min_lon, min_lat, max_lon, max_lat = coords

            # Create a Polygon from the bounding box coordinates
            # Polygon requires a closed ring, so we repeat the first point
            bbox_polygon = Polygon.from_bbox((min_lon, min_lat, max_lon, max_lat))

            # Filter geometries that intersect with the bounding box
            return queryset.filter(geometry__intersects=bbox_polygon)

        except (ValueError, TypeError):
            # If parsing fails, return unfiltered queryset
            return queryset
