import factory
import swapper
from django.contrib.gis.geos import Point, Polygon

from baseapp_core.models import DocumentId
from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.tests.factories import ProfileFactory

GeoJSONFeatureModel = swapper.load_model("baseapp_geo", "GeoJSONFeature")

SRID = 4326


def point_origin() -> Point:
    """Point at (0, 0)."""
    return Point(0, 0, srid=SRID)


def point_nyc() -> Point:
    """Empire State Building, New York City."""
    return Point(-73.9857, 40.7484, srid=SRID)


def point_east_of_origin() -> Point:
    """Exactly 0.01 deg east of the origin: ~1113 m at the equator."""
    return Point(0.01, 0, srid=SRID)


def unit_square_polygon() -> Polygon:
    """1x1 deg square centered on the origin."""
    polygon = Polygon.from_bbox((-0.5, -0.5, 0.5, 0.5))
    polygon.srid = SRID
    return polygon


def antimeridian_east() -> Point:
    """Point just east of the antimeridian (eastern hemisphere side)."""
    return Point(179.5, 0, srid=SRID)


def antimeridian_west() -> Point:
    """Point just west of the antimeridian (western hemisphere side)."""
    return Point(-179.5, 0, srid=SRID)


# Deterministic geometry fixtures for exact metric assertions (design section 10: no fuzzing).
POINT_ORIGIN = point_origin()
POINT_NYC = point_nyc()
POINT_EAST_OF_ORIGIN_1113M = point_east_of_origin()
UNIT_SQUARE_POLYGON = unit_square_polygon()
ANTIMERIDIAN_EAST = antimeridian_east()
ANTIMERIDIAN_WEST = antimeridian_west()


class AbstractGeoJSONFeatureFactory(factory.django.DjangoModelFactory):
    target = factory.SubFactory(UserFactory)
    target_document = factory.LazyAttribute(lambda o: DocumentId.get_or_create_for_object(o.target))
    geometry = factory.LazyFunction(point_origin)
    feature_type = ""

    class Meta:
        exclude = ["target"]
        abstract = True

    class Params:
        poi = factory.Trait(feature_type="poi")
        area = factory.Trait(
            feature_type="area",
            geometry=factory.LazyFunction(unit_square_polygon),
        )
        profile_target = factory.Trait(target=factory.SubFactory(ProfileFactory))


class GeoJSONFeatureFactory(AbstractGeoJSONFeatureFactory):
    class Meta:
        model = GeoJSONFeatureModel
