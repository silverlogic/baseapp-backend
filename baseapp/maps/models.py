from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.db import models as gis_models
from django.db import models
from model_utils.models import TimeStampedModel

from baseapp_core.graphql import RelayModel


class AbstractGeoJSONFeature(TimeStampedModel, RelayModel):
    """
    A GeoJSON feature that can be linked to any model via GenericForeignKey.
    Stores geographic data with geometry field and associates it with any Django model.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="geojson_features",
        help_text="User who created this feature",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255, db_index=True)
    geometry = gis_models.GeometryField(
        help_text="Geographic data in any geometry type (Point, LineString, Polygon, etc.)"
    )

    # Generic Foreign Key to link to any model
    target_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
    )
    target_object_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    target = GenericForeignKey("target_content_type", "target_object_id")

    class Meta:
        abstract = True
        verbose_name = "GeoJSON Feature"
        verbose_name_plural = "GeoJSON Features"
        indexes = [
            models.Index(fields=["target_content_type", "target_object_id"]),
        ]

    def __str__(self):
        return self.name


class GeoJSONFeature(AbstractGeoJSONFeature):
    """Concrete implementation of GeoJSON Feature model."""

    class Meta(AbstractGeoJSONFeature.Meta):
        swappable = "BASEAPP_MAPS_GEOJSONFEATURE_MODEL"
