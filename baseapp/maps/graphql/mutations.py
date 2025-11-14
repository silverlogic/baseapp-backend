import graphene
from django import forms
from django.apps import apps
from django.contrib.gis.geos import GEOSGeometry
from django.utils.translation import gettext_lazy as _
from graphene_django.forms.mutation import _set_errors_flag_to_context
from graphene_django.types import ErrorType
from graphql.error import GraphQLError

from baseapp_core.graphql import RelayMutation, get_obj_from_relay_id, login_required

from ..models import GeoJSONFeature
from .object_types import GeoJSONFeatureObjectType

app_label = GeoJSONFeature._meta.app_label


class GeoJSONInput(graphene.InputObjectType):
    """Input type for GeoJSON geometry data."""

    type = graphene.String(
        required=True, description="Geometry type (Point, Polygon, LineString, etc.)"
    )
    coordinates = graphene.Field(
        graphene.types.generic.GenericScalar,
        required=True,
        description="Coordinates array in GeoJSON format",
    )


class GeoJSONFeatureForm(forms.ModelForm):
    """Form for validating GeoJSON feature data."""

    class Meta:
        model = GeoJSONFeature
        fields = ("name",)


class GeoJSONFeatureCreate(RelayMutation):
    """
    Create a new GeoJSON feature and optionally link it to a target object.

    Requires authentication and permission to add GeoJSON features.
    """

    geojson_feature = graphene.Field(GeoJSONFeatureObjectType._meta.connection.Edge)

    class Input:
        target_object_id = graphene.ID(
            required=False, description="Relay ID of the target object to link this feature to"
        )
        name = graphene.String(required=True, description="Name of the feature")
        geometry = graphene.Field(
            GeoJSONInput, required=True, description="GeoJSON geometry (type and coordinates)"
        )

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        activity_name = f"{app_label}.add_geojsonfeature"

        if apps.is_installed("baseapp.activity_log"):
            from baseapp.activity_log.context import set_public_activity

            set_public_activity(verb=activity_name)

        # Resolve target if provided
        target = None
        if input.get("target_object_id"):
            target = get_obj_from_relay_id(info, input.get("target_object_id"))

            # Check permission to add feature to this target
            if not info.context.user.has_perm(activity_name, target):
                raise GraphQLError(
                    str(_("You don't have permission to add a feature to this object")),
                    extensions={"code": "permission_required"},
                )
        else:
            # Check general permission to add features
            if not info.context.user.has_perm(activity_name):
                raise GraphQLError(
                    str(_("You don't have permission to add features")),
                    extensions={"code": "permission_required"},
                )

        # Parse geometry from GeoJSON input
        geometry_input = input.get("geometry")
        try:
            geojson_dict = {
                "type": geometry_input["type"],
                "coordinates": geometry_input["coordinates"],
            }
            geometry = GEOSGeometry(str(geojson_dict).replace("'", '"'))
        except (KeyError, ValueError, TypeError) as e:
            raise GraphQLError(
                str(_("Invalid geometry data: %(error)s") % {"error": str(e)}),
                extensions={"code": "invalid_geometry"},
            )

        # Create the feature
        feature = GeoJSONFeature(
            user=info.context.user, name=input.get("name"), geometry=geometry, target=target
        )

        # Validate with form
        form = GeoJSONFeatureForm(instance=feature, data=input)
        if form.is_valid():
            feature.save()

            return cls(
                geojson_feature=GeoJSONFeatureObjectType._meta.connection.Edge(node=feature),
            )
        else:
            errors = ErrorType.from_errors(form.errors)
            _set_errors_flag_to_context(info)

            return cls(errors=errors)


class GeoJSONFeatureMutations(object):
    """All GeoJSON feature mutations."""

    geojson_feature_create = GeoJSONFeatureCreate.Field()
