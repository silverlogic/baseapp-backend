import pytest
from django.contrib.gis.geos import Point, Polygon

from ..models import GeoJSONFeature
from .factories import GeoJSONFeatureFactory

pytestmark = pytest.mark.django_db


class TestBoundingBoxFilter:
    """Test bounding box filtering for GeoJSON features."""

    def test_filter_features_within_bbox(self):
        """Test that features within the bounding box are returned."""
        # Create features at different locations
        # San Francisco: -122.4194, 37.7749
        sf_feature = GeoJSONFeatureFactory(name="San Francisco", geometry=Point(-122.4194, 37.7749))

        # Oakland: -122.2711, 37.8044
        oakland_feature = GeoJSONFeatureFactory(name="Oakland", geometry=Point(-122.2711, 37.8044))

        # New York: -74.0060, 40.7128 (outside bbox)
        GeoJSONFeatureFactory(name="New York", geometry=Point(-74.0060, 40.7128))

        # Bounding box covering San Francisco Bay Area
        # Format: "minLon,minLat,maxLon,maxLat"
        bbox = "-122.5,37.7,-122.2,37.9"

        # Apply filter
        from ..graphql.filters import GeoJSONFeatureFilter

        filterset = GeoJSONFeatureFilter(data={"bbox": bbox}, queryset=GeoJSONFeature.objects.all())

        results = list(filterset.qs)
        assert len(results) == 2
        assert sf_feature in results
        assert oakland_feature in results

    def test_filter_features_outside_bbox(self):
        """Test that features outside the bounding box are excluded."""
        # Create features outside the bbox
        GeoJSONFeatureFactory(name="Los Angeles", geometry=Point(-118.2437, 34.0522))
        GeoJSONFeatureFactory(name="Seattle", geometry=Point(-122.3321, 47.6062))

        # Bounding box covering only San Francisco area
        bbox = "-122.5,37.7,-122.3,37.8"

        from ..graphql.filters import GeoJSONFeatureFilter

        filterset = GeoJSONFeatureFilter(data={"bbox": bbox}, queryset=GeoJSONFeature.objects.all())

        assert filterset.qs.count() == 0

    def test_filter_polygon_intersects_bbox(self):
        """Test that polygons intersecting the bbox are included."""
        # Create a polygon that intersects with the bbox
        polygon = Polygon(
            (
                (-122.45, 37.75),
                (-122.40, 37.75),
                (-122.40, 37.80),
                (-122.45, 37.80),
                (-122.45, 37.75),
            )
        )

        feature = GeoJSONFeatureFactory(name="Golden Gate Park Area", geometry=polygon)

        # Bounding box that partially overlaps with the polygon
        bbox = "-122.42,37.76,-122.38,37.78"

        from ..graphql.filters import GeoJSONFeatureFilter

        filterset = GeoJSONFeatureFilter(data={"bbox": bbox}, queryset=GeoJSONFeature.objects.all())

        results = list(filterset.qs)
        assert len(results) == 1
        assert feature in results

    def test_invalid_bbox_format_returns_all(self):
        """Test that invalid bbox format doesn't filter results."""
        GeoJSONFeatureFactory()
        GeoJSONFeatureFactory()

        # Invalid bbox format (should have 4 coordinates)
        bbox = "-122.5,37.7"

        from ..graphql.filters import GeoJSONFeatureFilter

        filterset = GeoJSONFeatureFilter(data={"bbox": bbox}, queryset=GeoJSONFeature.objects.all())

        # Should return all features without filtering
        assert filterset.qs.count() == 2

    def test_empty_bbox_returns_all(self):
        """Test that empty bbox doesn't filter results."""
        GeoJSONFeatureFactory()
        GeoJSONFeatureFactory()

        from ..graphql.filters import GeoJSONFeatureFilter

        filterset = GeoJSONFeatureFilter(data={"bbox": ""}, queryset=GeoJSONFeature.objects.all())

        assert filterset.qs.count() == 2

    def test_no_bbox_returns_all(self):
        """Test that no bbox filter returns all features."""
        GeoJSONFeatureFactory()
        GeoJSONFeatureFactory()

        from ..graphql.filters import GeoJSONFeatureFilter

        filterset = GeoJSONFeatureFilter(data={}, queryset=GeoJSONFeature.objects.all())

        assert filterset.qs.count() == 2


class TestSearchFilter:
    """Test search filtering for GeoJSON features."""

    def test_search_by_name(self):
        """Test searching features by name."""
        feature = GeoJSONFeatureFactory(name="Golden Gate Bridge")
        GeoJSONFeatureFactory(name="Bay Bridge")

        from ..graphql.filters import GeoJSONFeatureFilter

        filterset = GeoJSONFeatureFilter(
            data={"q": "Golden"}, queryset=GeoJSONFeature.objects.all()
        )

        results = list(filterset.qs)
        assert len(results) == 1
        assert feature in results

    def test_search_case_insensitive(self):
        """Test that search is case insensitive."""
        feature = GeoJSONFeatureFactory(name="Golden Gate Bridge")

        from ..graphql.filters import GeoJSONFeatureFilter

        filterset = GeoJSONFeatureFilter(
            data={"q": "golden"}, queryset=GeoJSONFeature.objects.all()
        )

        results = list(filterset.qs)
        assert len(results) == 1
        assert feature in results


class TestOrderingFilter:
    """Test ordering of GeoJSON features."""

    def test_order_by_created_ascending(self):
        """Test ordering by created timestamp ascending."""
        feature1 = GeoJSONFeatureFactory(name="First")
        feature2 = GeoJSONFeatureFactory(name="Second")
        feature3 = GeoJSONFeatureFactory(name="Third")

        from ..graphql.filters import GeoJSONFeatureFilter

        filterset = GeoJSONFeatureFilter(
            data={"order_by": "created"}, queryset=GeoJSONFeature.objects.all()
        )

        results = list(filterset.qs)
        assert results[0] == feature1
        assert results[1] == feature2
        assert results[2] == feature3

    def test_order_by_created_descending(self):
        """Test ordering by created timestamp descending."""
        feature1 = GeoJSONFeatureFactory(name="First")
        feature2 = GeoJSONFeatureFactory(name="Second")
        feature3 = GeoJSONFeatureFactory(name="Third")

        from ..graphql.filters import GeoJSONFeatureFilter

        filterset = GeoJSONFeatureFilter(
            data={"order_by": "-created"}, queryset=GeoJSONFeature.objects.all()
        )

        results = list(filterset.qs)
        assert results[0] == feature3
        assert results[1] == feature2
        assert results[2] == feature1

    def test_order_by_name(self):
        """Test ordering by name alphabetically."""
        GeoJSONFeatureFactory(name="Zebra")
        feature_apple = GeoJSONFeatureFactory(name="Apple")
        GeoJSONFeatureFactory(name="Mango")

        from ..graphql.filters import GeoJSONFeatureFilter

        filterset = GeoJSONFeatureFilter(
            data={"order_by": "name"}, queryset=GeoJSONFeature.objects.all()
        )

        results = list(filterset.qs)
        assert results[0] == feature_apple
