import factory
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.geos import Point

from ..models import GeoJSONFeature


def get_content_type(field_name):
    """Helper to get content type from a generic foreign key field."""

    def _obj_content_type(obj):
        if not hasattr(obj, field_name):
            return None
        fk_obj = getattr(obj, field_name, None)
        if fk_obj:
            return ContentType.objects.get_for_model(fk_obj)

    return _obj_content_type


def get_obj_pk(field_name):
    """Helper to get pk from a generic foreign key field."""

    def _obj_id(obj):
        if not hasattr(obj, field_name):
            return None
        fk_obj = getattr(obj, field_name)
        return fk_obj.pk if fk_obj else None

    return _obj_id


class GeoJSONFeatureFactory(factory.django.DjangoModelFactory):
    """Factory for creating GeoJSONFeature instances."""

    name = factory.Faker("city")
    geometry = factory.LazyFunction(lambda: Point(-122.4194, 37.7749))  # San Francisco coordinates
    user = None  # Optional, can be set when creating the feature

    target_object_id = factory.LazyAttribute(get_obj_pk("target"))
    target_content_type = factory.LazyAttribute(get_content_type("target"))

    class Meta:
        model = GeoJSONFeature

    def __setattr__(self, name, value):
        """Override to automatically set content type and object id when target is set."""
        super().__setattr__(name, value)
        if name in ["target"]:
            setattr(self, f"{name}_content_type", ContentType.objects.get_for_model(value))
            setattr(self, f"{name}_object_id", value.id)
