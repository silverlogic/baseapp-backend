import swapper
from django import forms
from django.contrib.gis.geos import GEOSGeometry
from django.utils.translation import gettext_lazy as _

from ..models import ALLOWED_GEOMETRY_TYPES

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


class GeoMutations:
    pass
