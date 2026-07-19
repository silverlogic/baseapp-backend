import graphene
import pytest
import swapper
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import LineString
from django.core.exceptions import ValidationError

from baseapp_geo.models import AbstractGeoJSONFeature

from .factories import POINT_NYC, UNIT_SQUARE_POLYGON, GeoJSONFeatureFactory

pytestmark = pytest.mark.django_db

GeoJSONFeature = swapper.load_model("baseapp_geo", "GeoJSONFeature")
Profile = swapper.load_model("baseapp_profiles", "Profile")
User = get_user_model()


def test_saves_with_blank_name_and_description():
    feature = GeoJSONFeatureFactory(name="", description="")
    feature.full_clean()
    feature.refresh_from_db()

    assert feature.name == ""
    assert feature.description == ""


def test_saves_point_geometry():
    feature = GeoJSONFeatureFactory(geometry=POINT_NYC)
    feature.refresh_from_db()

    assert feature.geometry.geom_type == "Point"
    assert list(feature.geometry.coords) == pytest.approx([-73.9857, 40.7484])


def test_saves_polygon_geometry():
    feature = GeoJSONFeatureFactory(area=True)
    feature.refresh_from_db()

    assert feature.geometry.geom_type == "Polygon"
    assert feature.geometry.equals(UNIT_SQUARE_POLYGON)


def test_clean_rejects_linestring_geometry():
    feature = GeoJSONFeatureFactory()
    feature.geometry = LineString((0, 0), (1, 1), srid=4326)

    with pytest.raises(ValidationError) as exc_info:
        feature.full_clean()

    assert "geometry" in exc_info.value.message_dict


def test_swapper_resolves_concrete_model():
    assert issubclass(GeoJSONFeature, AbstractGeoJSONFeature)
    assert GeoJSONFeature._meta.abstract is False
    assert GeoJSONFeature._meta.label == settings.BASEAPP_GEO_GEOJSONFEATURE_MODEL


def test_get_graphql_object_type_returns_object_type():
    object_type = GeoJSONFeature.get_graphql_object_type()

    assert isinstance(object_type, type)
    assert issubclass(object_type, graphene.ObjectType)


def test_attaches_to_two_distinct_target_models():
    user_feature = GeoJSONFeatureFactory()
    profile_feature = GeoJSONFeatureFactory(profile_target=True)

    assert isinstance(user_feature.target, User)
    assert isinstance(profile_feature.target, Profile)
    assert user_feature.target_document.content_type != profile_feature.target_document.content_type


def test_cascade_deletes_feature_when_user_target_deleted():
    feature = GeoJSONFeatureFactory()
    feature.target.delete()

    assert not GeoJSONFeature.objects.filter(pk=feature.pk).exists()


def test_cascade_deletes_feature_when_profile_target_deleted():
    feature = GeoJSONFeatureFactory(profile_target=True)
    feature.target.delete()

    assert not GeoJSONFeature.objects.filter(pk=feature.pk).exists()
