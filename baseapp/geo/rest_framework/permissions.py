import swapper
from rest_framework.permissions import BasePermission


class CanViewGeoJSONFeatures(BasePermission):
    """Read access to features, as decided by the `view_geojsonfeature` permission.

    Goes through `has_perm`, so a project that overrides `GeoPermissionsBackend` (e.g. to hide
    features from anonymous users) gets the same rule on the REST endpoints as on GraphQL.
    """

    def has_permission(self, request, view) -> bool:
        GeoJSONFeature = swapper.load_model("baseapp_geo", "GeoJSONFeature")
        return request.user.has_perm(f"{GeoJSONFeature._meta.app_label}.view_geojsonfeature")
