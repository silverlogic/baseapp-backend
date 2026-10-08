import json
from typing import Optional

import graphene
import swapper
from django.db.models import Model, QuerySet
from django.utils.translation import gettext_lazy as _
from graphene.types.generic import GenericScalar
from query_optimizer.optimizer import QueryOptimizer
from query_optimizer.typing import TModel

from baseapp_auth.graphql import PermissionsInterface
from baseapp_core.graphql import DjangoObjectType
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.graphql.utils import resolve_document_content_object

from .filters import GeoJSONFeatureFilter

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

    # Root here is the GeoJSONFeature itself (`resolve_properties` returns `self`). Going
    # through the request-scoped cache keeps a connection whose features share a target to
    # one fetch per target instead of one per row.
    def resolve_target(self, info) -> Optional[Model]:
        document = self.target_document
        target = resolve_document_content_object(document, info)
        if target is not None and not hasattr(target, "mapped_public_id"):
            # The target's own relay id is this document's public_id, already loaded.
            # Seeding it is what PublicIdResolver reads instead of querying DocumentId per row.
            target.mapped_public_id = document.public_id
        return target


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
        # Pinned to the default model name so it stays stable under swapping (NFR-7) AND
        # matches baseapp_core's public-id node lookup, which resolves the schema type by
        # `model_class().__name__`.
        name = "GeoJSONFeature"
        interfaces = (RelayNode, PermissionsInterface)
        fields = ("id", "type", "bbox", "geometry", "properties")
        # On Meta, not on the connection field: DjangoConnectionField reads it from here.
        filterset_class = GeoJSONFeatureFilter

    def resolve_type(self, info) -> str:
        return "Feature"

    def resolve_bbox(self, info) -> Optional[tuple]:
        return self.geometry.extent if self.geometry else None

    def resolve_geometry(self, info) -> dict:
        return json.loads(self.geometry.geojson)

    def resolve_properties(self, info) -> "GeoJSONFeature":
        return self

    @classmethod
    def pre_optimization_hook(
        cls, queryset: QuerySet[TModel], optimizer: QueryOptimizer
    ) -> QuerySet[TModel]:
        """Preload what the resolvers read but GraphQL defers.

        - `target_document` (+ its content type): `resolve_target` walks the FK, which is one
          query per feature without this.
        - every column behind `properties`: `GeoJSONFeatureProperties` is a plain graphene
          type resolved by attribute access on the feature, so the optimizer cannot see
          that `properties { featureType }` reads a model column and defers it.
        - `geometry`: `resolve_bbox` and `resolve_geometry` both read it, so a query asking
          only for `bbox` would defer the column and refetch it per row.
        """
        queryset = super().pre_optimization_hook(queryset, optimizer)
        queryset = queryset.select_related(
            "target_document", "target_document__content_type"
        ).prefetch_related("target_document__content_object")
        for field_name in (
            "geometry",
            "target_document_id",
            "name",
            "description",
            "feature_type",
            "created",
            "modified",
        ):
            if field_name not in optimizer.only_fields:
                optimizer.only_fields.append(field_name)
        return queryset

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
