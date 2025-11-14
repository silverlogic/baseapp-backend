from .models import GeoJSONFeature


class GeoJSONFeaturesPermissionsBackend:
    """
    Custom permissions backend for GeoJSON features.

    Allows any authenticated user to add features by default.
    """

    def authenticate(self, request, **kwargs):
        return None

    def has_perm(self, user_obj, perm, obj=None):
        if not user_obj.is_active:
            return False

        app_label = GeoJSONFeature._meta.app_label
        model_name = GeoJSONFeature._meta.model_name

        # Permission to add a feature
        if perm == f"{app_label}.add_{model_name}":
            # Any authenticated user can add features
            return user_obj.is_authenticated

        # Permission to change a feature
        if perm == f"{app_label}.change_{model_name}":
            if obj is None:
                return False
            # Only the creator can change their own feature
            return obj.user == user_obj

        # Permission to delete a feature
        if perm == f"{app_label}.delete_{model_name}":
            if obj is None:
                return False
            # Only the creator can delete their own feature
            return obj.user == user_obj

        return None
