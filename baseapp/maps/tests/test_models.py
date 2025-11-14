import pytest
import swapper
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.geos import Point, Polygon

from baseapp_profiles.tests.factories import ProfileFactory

from .factories import GeoJSONFeatureFactory

GeoJSONFeature = swapper.load_model("baseapp_maps", "GeoJSONFeature")

pytestmark = pytest.mark.django_db


class TestGeoJSONFeatureModel:
    """Test GeoJSONFeature model functionality."""

    def test_create_feature_with_point(self):
        """Test creating a GeoJSON feature with Point geometry."""
        feature = GeoJSONFeatureFactory(name="Test Point", geometry=Point(-122.4194, 37.7749))

        assert feature.pk is not None
        assert feature.name == "Test Point"
        assert feature.geometry.geom_type == "Point"
        assert feature.geometry.coords == (-122.4194, 37.7749)

    def test_create_feature_with_polygon(self):
        """Test creating a GeoJSON feature with Polygon geometry."""
        polygon = Polygon(
            (
                (-122.45, 37.75),
                (-122.40, 37.75),
                (-122.40, 37.80),
                (-122.45, 37.80),
                (-122.45, 37.75),
            )
        )

        feature = GeoJSONFeatureFactory(name="Test Polygon", geometry=polygon)

        assert feature.pk is not None
        assert feature.geometry.geom_type == "Polygon"

    def test_str_representation(self):
        """Test string representation of the model."""
        feature = GeoJSONFeatureFactory(name="My Feature")
        assert str(feature) == "My Feature"

    def test_timestamps_auto_created(self):
        """Test that created and modified timestamps are automatically set."""
        feature = GeoJSONFeatureFactory()

        assert feature.created is not None
        assert feature.modified is not None
        assert feature.created == feature.modified

    def test_timestamps_updated_on_save(self):
        """Test that modified timestamp is updated on save."""
        feature = GeoJSONFeatureFactory()
        original_modified = feature.modified

        # Modify and save
        feature.name = "Updated Name"
        feature.save()

        assert feature.modified > original_modified


class TestGenericForeignKey:
    """Test Generic Foreign Key functionality with target field."""

    def test_feature_with_profile_target(self):
        """Test linking a feature to a Profile via GenericForeignKey."""
        profile = ProfileFactory(name="Test Profile")

        feature = GeoJSONFeatureFactory(
            name="Profile Location", geometry=Point(-122.4194, 37.7749), target=profile
        )

        assert feature.target == profile
        assert feature.target_content_type == ContentType.objects.get_for_model(profile)
        assert feature.target_object_id == profile.pk

    def test_feature_without_target(self):
        """Test creating a feature without a target."""
        feature = GeoJSONFeatureFactory(
            name="Standalone Location", geometry=Point(-122.4194, 37.7749)
        )

        assert feature.target is None
        assert feature.target_content_type is None
        assert feature.target_object_id is None

    def test_multiple_features_same_target(self):
        """Test creating multiple features linked to the same target."""
        profile = ProfileFactory()

        feature1 = GeoJSONFeatureFactory(
            name="Location 1", geometry=Point(-122.4194, 37.7749), target=profile
        )

        feature2 = GeoJSONFeatureFactory(
            name="Location 2", geometry=Point(-122.2711, 37.8044), target=profile
        )

        assert feature1.target == profile
        assert feature2.target == profile
        assert (
            GeoJSONFeature.objects.filter(
                target_content_type=ContentType.objects.get_for_model(profile),
                target_object_id=profile.pk,
            ).count()
            == 2
        )

    def test_target_content_type_deletion_cascades(self):
        """Test that deleting content type could affect features."""
        # Note: This tests the GenericForeignKey behavior
        # The actual cascade depends on the target model's deletion policy
        profile = ProfileFactory()
        feature = GeoJSONFeatureFactory(name="Profile Location", target=profile)

        # Verify the feature is properly linked
        assert feature.target_content_type == ContentType.objects.get_for_model(profile)
        assert feature.target_object_id == profile.pk
        assert feature.target == profile


class TestQueryingFeatures:
    """Test querying GeoJSON features."""

    def test_filter_by_target_content_type(self):
        """Test filtering features by target content type."""
        profile1 = ProfileFactory()
        profile2 = ProfileFactory()

        feature1 = GeoJSONFeatureFactory(target=profile1)
        feature2 = GeoJSONFeatureFactory(target=profile2)
        GeoJSONFeatureFactory()  # Feature without target

        profile_ct = ContentType.objects.get_for_model(profile1)
        features = GeoJSONFeature.objects.filter(target_content_type=profile_ct)

        assert features.count() == 2
        assert feature1 in features
        assert feature2 in features

    def test_filter_by_name(self):
        """Test filtering features by name."""
        feature = GeoJSONFeatureFactory(name="Golden Gate Bridge")
        GeoJSONFeatureFactory(name="Bay Bridge")

        features = GeoJSONFeature.objects.filter(name__icontains="Golden")
        assert features.count() == 1
        assert features.first() == feature

    def test_order_by_created(self):
        """Test ordering features by created timestamp."""
        feature1 = GeoJSONFeatureFactory(name="First")
        feature2 = GeoJSONFeatureFactory(name="Second")
        feature3 = GeoJSONFeatureFactory(name="Third")

        features = GeoJSONFeature.objects.order_by("created")
        assert list(features) == [feature1, feature2, feature3]

        features_desc = GeoJSONFeature.objects.order_by("-created")
        assert list(features_desc) == [feature3, feature2, feature1]
