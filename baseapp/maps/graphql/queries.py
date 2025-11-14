import graphene
from graphene_django.filter import DjangoFilterConnectionField

from .object_types import GeoJSONFeatureObjectType


class GeoJSONFeaturesQueries:
    """GraphQL queries for GeoJSON features."""

    geojson_feature = graphene.relay.Node.Field(
        GeoJSONFeatureObjectType, description="Fetch a single GeoJSON feature by ID"
    )

    all_geojson_features = DjangoFilterConnectionField(
        GeoJSONFeatureObjectType,
        description="Fetch all GeoJSON features with optional filtering by bbox, search, and ordering",
    )

    def resolve_all_geojson_features(self, info, **kwargs):
        """
        Resolve all GeoJSON features.

        Supports filtering by:
        - bbox: Bounding box filter (format: "minLon,minLat,maxLon,maxLat")
        - q: Search by name
        - target_content_type: Filter by content type ID
        - order_by: Sort results

        Add permission checks here if needed.
        """
        return GeoJSONFeatureObjectType._meta.model.objects.all()
