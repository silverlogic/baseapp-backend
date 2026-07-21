import swapper
from django.contrib.gis.db import models as gis_models
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.graphql import RelayModel
from baseapp_core.models import DocumentIdMixin, DocumentIdTargetMixin

ALLOWED_GEOMETRY_TYPES = ("Point", "Polygon")


class AbstractGeoJSONFeature(DocumentIdTargetMixin, TimeStampedModel, DocumentIdMixin, RelayModel):
    name = models.CharField(_("name"), max_length=255, blank=True, default="")
    description = models.TextField(_("description"), blank=True, default="")
    feature_type = models.CharField(
        _("feature type"), max_length=100, blank=True, default="", db_index=True
    )
    geometry = gis_models.GeometryField(_("geometry"), geography=True, srid=4326)

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_geo", "GeoJSONFeature")
        verbose_name = _("geojson feature")
        verbose_name_plural = _("geojson features")

    def __str__(self) -> str:
        return self.name or f"GeoJSONFeature ({self.pk})"

    def clean(self) -> None:
        super().clean()
        if self.geometry and self.geometry.geom_type not in ALLOWED_GEOMETRY_TYPES:
            raise ValidationError({"geometry": [_("Geometry must be a Point or a Polygon.")]})

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import GeoJSONFeatureObjectType

        return GeoJSONFeatureObjectType
