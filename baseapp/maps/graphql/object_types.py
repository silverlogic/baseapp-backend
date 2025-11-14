import graphene
import swapper
from graphene import relay
from graphene_django import DjangoObjectType

from .filters import GeoJSONFeatureFilter

GeoJSONFeature = swapper.load_model("baseapp_maps", "GeoJSONFeature")


class GeoJSONType(graphene.ObjectType):
    """Represents a GeoJSON geometry object."""

    type = graphene.String(required=True)
    coordinates = graphene.Field(graphene.types.generic.GenericScalar, required=True)


class BaseGeoJSONFeatureObjectType:
    """Base GeoJSON Feature GraphQL Object Type with geometry serialization."""

    target = graphene.Field(relay.Node)
    geojson = graphene.Field(GeoJSONType, description="GeoJSON representation of the geometry")

    class Meta:
        model = GeoJSONFeature
        # Note: geometry field is excluded, use geojson field instead
        fields = (
            "id",
            "user",
            "name",
            "target_content_type",
            "target_object_id",
            "target",
            "created",
            "modified",
        )
        filterset_class = GeoJSONFeatureFilter
        interfaces = (relay.Node,)

    # def resolve_target(self, info):
    #     """
    #     Resolve the target GenericForeignKey to its GraphQL node representation.

    #     Returns the target object as a relay Node if it exists and has a registered
    #     GraphQL ObjectType.
    #     """
    #     if not self.target:
    #         return None

    #     try:
    #         # Get the GraphQL ObjectType for the target model
    #         object_type = get_object_type_for_model(self.target.__class__)
    #         if object_type:
    #             return self.target
    #     except Exception:
    #         pass

    #     return None

    def resolve_geojson(self, info):
        """
        Serialize the geometry field to GeoJSON format.

        Returns a dict with 'type' and 'coordinates' matching GeoJSON spec.
        """
        if not self.geometry:
            return None

        def coords_to_list(coords):
            """Recursively convert coordinate tuples to lists for JSON serialization."""
            if isinstance(coords, (list, tuple)):
                # Check if it's a coordinate pair (numbers)
                if len(coords) > 0 and isinstance(coords[0], (int, float)):
                    return list(coords)
                # Otherwise it's nested, recurse
                return [coords_to_list(item) for item in coords]
            return coords

        return {
            "type": self.geometry.geom_type,
            "coordinates": coords_to_list(self.geometry.coords),
        }

    @classmethod
    def get_queryset(cls, queryset, info):
        """
        Customize the queryset with optimizations and permissions.

        Override this method in subclasses to add permission checks.
        """
        return queryset.select_related("target_content_type")


class GeoJSONFeatureObjectType(BaseGeoJSONFeatureObjectType, DjangoObjectType):
    """GraphQL Object Type for GeoJSON Feature."""

    class Meta(BaseGeoJSONFeatureObjectType.Meta):
        pass
