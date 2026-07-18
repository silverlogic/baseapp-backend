import json
from typing import Optional

import graphene
import swapper
from django.utils.translation import gettext_lazy as _
from graphene.types.generic import GenericScalar

from baseapp_auth.graphql import PermissionsInterface
from baseapp_core.graphql import DjangoObjectType
from baseapp_core.graphql import Node as RelayNode

# Side effect: registers the upstream GeometryField -> GraphQL converter needed
# before any DjangoObjectType over a model with a GeometryField is constructed.
from .scalars import Geometry  # noqa: F401  isort:skip

GeoJSONFeature = swapper.load_model("baseapp_geo", "GeoJSONFeature")
app_label = GeoJSONFeature._meta.app_label


class GeometryObjectType(graphene.ObjectType):
    class Meta:
        name = "GeometryObjectType"
        description = _("GeoJSON geometry object (RFC 7946).")

    type = graphene.String(required=True, description=_("Geometry type, e.g. Point or Polygon."))
    coordinates = GenericScalar(
        required=True, description=_("Geometry coordinates in [lng, lat] order.")
    )


class GeoJSONFeatureProperties(graphene.ObjectType):
    class Meta:
        name = "GeoJSONFeatureProperties"
        description = _("Feature properties (RFC 7946 `properties` member).")

    name = graphene.String(required=True, description=_("Human-readable name of the feature."))
    description = graphene.String(required=True, description=_("Description of the feature."))
    feature_type = graphene.String(
        required=True, description=_("Free-form feature type used for filtering.")
    )
    target = graphene.Field(RelayNode, description=_("The object this feature is attached to."))
    created = graphene.DateTime(
        required=True, description=_("When the feature was created (UTC, ISO 8601).")
    )
    modified = graphene.DateTime(
        required=True, description=_("When the feature was last modified (UTC, ISO 8601).")
    )


class BaseGeoJSONFeatureObjectType:
    type = graphene.String(required=True, description=_('Constant "Feature" (RFC 7946).'))
    bbox = graphene.List(
        graphene.Float,
        description=_("Bounding box of the geometry as [west, south, east, north]."),
    )
    geometry = graphene.Field(
        GeometryObjectType, required=True, description=_("Geometry of the feature.")
    )
    properties = graphene.Field(
        GeoJSONFeatureProperties, required=True, description=_("Properties of the feature.")
    )

    class Meta:
        model = GeoJSONFeature
        name = "GeoJSONFeatureObjectType"
        interfaces = (RelayNode, PermissionsInterface)
        fields = ("id", "type", "bbox", "geometry", "properties")

    def resolve_type(self, info) -> str:
        return "Feature"

    def resolve_bbox(self, info) -> Optional[tuple]:
        return self.geometry.extent if self.geometry else None

    def resolve_geometry(self, info) -> dict:
        return json.loads(self.geometry.geojson)

    def resolve_properties(self, info) -> "GeoJSONFeature":
        return self

    @classmethod
    def get_node(
        cls, info: graphene.ResolveInfo, id: str
    ) -> Optional["BaseGeoJSONFeatureObjectType"]:
        if not info.context.user.has_perm(f"{app_label}.view_geojsonfeature"):
            return None
        return super().get_node(info, id)


class GeoJSONFeatureObjectType(BaseGeoJSONFeatureObjectType, DjangoObjectType):
    class Meta(BaseGeoJSONFeatureObjectType.Meta):
        pass
