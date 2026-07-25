import swapper
from django.contrib.auth.backends import BaseBackend


class GeoPermissionsBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None) -> bool:
        GeoJSONFeature = swapper.load_model("baseapp_geo", "GeoJSONFeature")
        app_label = GeoJSONFeature._meta.app_label

        if perm == f"{app_label}.view_geojsonfeature":
            return True

        if perm == f"{app_label}.add_geojsonfeature":
            return user_obj.is_authenticated

        return False
