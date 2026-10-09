import logging

import graphene
import swapper
from django import forms
from django.apps import apps
from django.contrib.gis.geos import GEOSGeometry
from django.utils.translation import gettext_lazy as _
from graphene_django.forms.mutation import _set_errors_flag_to_context
from graphene_django.types import ErrorType
from graphql.error import GraphQLError

from baseapp_core.graphql import Node as RelayNode
from baseapp_core.graphql import RelayMutation, get_obj_from_relay_id

from ..models import ALLOWED_GEOMETRY_TYPES
from .scalars import Geometry

logger = logging.getLogger(__name__)

GeoJSONFeature = swapper.load_model("baseapp_geo", "GeoJSONFeature")
app_label = GeoJSONFeature._meta.app_label
ObjectType = GeoJSONFeature.get_graphql_object_type()


def _resolve_relay_id(info: graphene.ResolveInfo, relay_id):
    """Resolve a relay ID, treating any failure as "not found".

    Never let the resolver's own exception reach the client: it leaks which IDs exist.
    """
    try:
        return get_obj_from_relay_id(info, relay_id)
    except Exception:
        logger.exception("Could not resolve relay id in a geo mutation")
        return None


def _get_feature(info: graphene.ResolveInfo, relay_id) -> "GeoJSONFeature":
    """Resolve a relay ID to a GeoJSONFeature, or raise `not_found`.

    `get_obj_from_relay_id` resolves a public ID through DocumentId and returns the object
    of ANY registered model, so this type check is what stops these mutations from writing
    to (or deleting) another block's rows.
    """
    obj = _resolve_relay_id(info, relay_id)
    if not isinstance(obj, GeoJSONFeature):
        raise GraphQLError(
            str(_("GeoJSON feature not found")),
            extensions={"code": "not_found"},
        )
    return obj


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

        target = _resolve_relay_id(info, input.get("target_object_id"))
        if target is None:
            raise GraphQLError(
                str(_("Target object not found")),
                extensions={"code": "not_found"},
            )

        instance = GeoJSONFeature(target=target, created_by=info.context.user)
        if apps.is_installed("baseapp_profiles"):
            instance.profile = getattr(info.context.user, "current_profile", None)

        form = GeoJSONFeatureForm(instance=instance, data=input)
        if form.is_valid():
            obj = form.save()

            return cls(geo_feature=ObjectType._meta.connection.Edge(node=obj))
        else:
            errors = ErrorType.from_errors(form.errors)
            _set_errors_flag_to_context(info)

            return cls(errors=errors)


class GeoJSONFeatureUpdate(RelayMutation):
    """Update an existing GeoJSON feature."""

    geo_feature = graphene.Field(
        ObjectType,
        description=_("The updated GeoJSON feature."),
    )

    class Input:
        id = graphene.ID(
            required=True,
            description=_("Relay global ID of the GeoJSON feature to update."),
        )
        geometry = Geometry(
            required=False,
            description=_("New feature geometry as GeoJSON or WKT; must be a Point or a Polygon."),
        )
        name = graphene.String(
            required=False, description=_("New human-readable name for the feature.")
        )
        description = graphene.String(
            required=False, description=_("New free-text description of the feature.")
        )
        feature_type = graphene.String(
            required=False, description=_("New type label used to categorize the feature.")
        )

    @classmethod
    def mutate_and_get_payload(
        cls, root, info: graphene.ResolveInfo, **input
    ) -> "GeoJSONFeatureUpdate":
        """Permission-check, overlay input onto instance values, validate and save."""
        instance = _get_feature(info, input.get("id"))
        if not info.context.user.has_perm(f"{app_label}.change_geojsonfeature", instance):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        data = {
            field: input[field] if field in input else getattr(instance, field)
            for field in GeoJSONFeatureForm.Meta.fields
        }

        form = GeoJSONFeatureForm(instance=instance, data=data)
        if form.is_valid():
            obj = form.save()

            return cls(geo_feature=obj)
        else:
            errors = ErrorType.from_errors(form.errors)
            _set_errors_flag_to_context(info)

            return cls(errors=errors)


class GeoJSONFeatureDelete(RelayMutation):
    """Delete an existing GeoJSON feature."""

    deleted_id = graphene.ID(
        description=_("Relay global ID of the deleted GeoJSON feature."),
    )
    target = graphene.Field(
        RelayNode,
        description=_("The object the deleted feature was attached to."),
    )

    class Input:
        id = graphene.ID(
            required=True,
            description=_("Relay global ID of the GeoJSON feature to delete."),
        )

    @classmethod
    def mutate_and_get_payload(
        cls, root, info: graphene.ResolveInfo, **input
    ) -> "GeoJSONFeatureDelete":
        """Permission-check, capture the target, and delete the feature."""
        relay_id = input.get("id")
        obj = _get_feature(info, relay_id)
        if not info.context.user.has_perm(f"{app_label}.delete_geojsonfeature", obj):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        target = obj.target

        obj.delete()

        return cls(deleted_id=relay_id, target=target)


class GeoMutations:
    geo_feature_create = GeoJSONFeatureCreate.Field()
    geo_feature_update = GeoJSONFeatureUpdate.Field()
    geo_feature_delete = GeoJSONFeatureDelete.Field()
