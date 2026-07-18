import factory
import swapper
from django.contrib.gis.geos import Point

from baseapp_core.models import DocumentId
from baseapp_core.tests.factories import UserFactory

GeoJSONFeatureModel = swapper.load_model("baseapp_geo", "GeoJSONFeature")


class AbstractGeoJSONFeatureFactory(factory.django.DjangoModelFactory):
    target = factory.SubFactory(UserFactory)
    target_document = factory.LazyAttribute(lambda o: DocumentId.get_or_create_for_object(o.target))
    geometry = factory.LazyFunction(lambda: Point(0, 0, srid=4326))

    class Meta:
        exclude = ["target"]
        abstract = True


class GeoJSONFeatureFactory(AbstractGeoJSONFeatureFactory):
    class Meta:
        model = GeoJSONFeatureModel
