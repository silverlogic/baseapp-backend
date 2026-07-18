import graphene
import swapper
from django import forms
from django.contrib.gis.geos import GEOSGeometry
from django.utils.translation import gettext_lazy as _
from graphene_django.forms.mutation import _set_errors_flag_to_context
from graphene_django.types import ErrorType
from graphql.error import GraphQLError

from baseapp_core.graphql import RelayMutation, get_obj_from_relay_id

from ..models import ALLOWED_GEOMETRY_TYPES
from .scalars import Geometry

GeoJSONFeature = swapper.load_model("baseapp_geo", "GeoJSONFeature")
app_label = GeoJSONFeature._meta.app_label
ObjectType = GeoJSONFeature.get_graphql_object_type()


class GeoJSONFeatureForm(forms.ModelForm):
    class Meta:
        model = GeoJSONFeature
        fields = ("name", "description", "feature_type", "geometry")

    def clean_geometry(self) -> GEOSGeometry:
        geometry = self.cleaned_data.get("geometry")
        if geometry and geometry.geom_type not in ALLOWED_GEOMETRY_TYPES:
            raise forms.ValidationError(_("Geometry must be a Point or a Polygon."))
        return geometry


class GeoJSONFeatureCreate(RelayMutation):
    """Create a GeoJSON feature attached to a target object."""

    geo_feature = graphene.Field(
        ObjectType._meta.connection.Edge,
        description=_("Edge wrapping the newly created GeoJSON feature."),
    )

    class Input:
        target_object_id = graphene.ID(
            required=True,
            description=_("Relay global ID of the object the feature is attached to."),
        )
        geometry = Geometry(
            required=True,
            description=_("Feature geometry as GeoJSON or WKT; must be a Point or a Polygon."),
        )
        name = graphene.String(
            required=False, description=_("Optional human-readable name for the feature.")
        )
        description = graphene.String(
            required=False, description=_("Optional free-text description of the feature.")
        )
        feature_type = graphene.String(
            required=False, description=_("Optional type label used to categorize the feature.")
        )

    @classmethod
    def mutate_and_get_payload(
        cls, root, info: graphene.ResolveInfo, **input
    ) -> "GeoJSONFeatureCreate":
        """Permission-check, validate via GeoJSONFeatureForm, and create the feature."""
        if not info.context.user.has_perm(f"{app_label}.add_geojsonfeature"):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        target = get_obj_from_relay_id(info, input.get("target_object_id"))
        instance = GeoJSONFeature(target=target)

        form = GeoJSONFeatureForm(instance=instance, data=input)
        if form.is_valid():
            obj = form.save()

            return cls(geo_feature=ObjectType._meta.connection.Edge(node=obj))
        else:
            errors = ErrorType.from_errors(form.errors)
            _set_errors_flag_to_context(info)

            return cls(errors=errors)


class GeoMutations:
    pass
