import pytest
from django.contrib.gis.geos import Point, Polygon

from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.tests.factories import ProfileFactory

from .factories import GeoJSONFeatureFactory

pytestmark = pytest.mark.django_db


# GraphQL Queries
ALL_GEOJSON_FEATURES_QUERY = """
    query AllGeoJSONFeatures($bbox: String, $q: String, $orderBy: String) {
        allGeojsonFeatures(bbox: $bbox, q: $q, orderBy: $orderBy) {
            edges {
                node {
                    id
                    name
                    geojson {
                        type
                        coordinates
                    }
                    created
                    modified
                }
            }
        }
    }
"""

GEOJSON_FEATURE_WITH_TARGET_QUERY = """
    query GeoJSONFeatureWithTarget($id: ID!) {
        node(id: $id) {
            ... on GeoJSONFeatureObjectType {
                id
                name
                geojson {
                    type
                    coordinates
                }
                target {
                    id
                    __typename
                    ... on Profile {
                        name
                        owner {
                            id
                            email
                        }
                    }
                }
                created
            }
        }
    }
"""

GEOJSON_FEATURE_QUERY = """
    query GeoJSONFeature($id: ID!) {
        geojsonFeature(id: $id) {
            id
            name
            geojson {
                type
                coordinates
            }
        }
    }
"""


class TestAllGeoJSONFeaturesQuery:
    """Test querying all GeoJSON features."""

    def test_query_all_features(self, graphql_client):
        """Test querying all GeoJSON features."""
        feature1 = GeoJSONFeatureFactory(name="Feature 1")
        feature2 = GeoJSONFeatureFactory(name="Feature 2")

        response = graphql_client(ALL_GEOJSON_FEATURES_QUERY)
        content = response.json()

        edges = content["data"]["allGeojsonFeatures"]["edges"]
        assert len(edges) == 2

        # Check that features are returned
        returned_ids = [edge["node"]["id"] for edge in edges]
        assert feature1.relay_id in returned_ids
        assert feature2.relay_id in returned_ids

    def test_query_with_bbox_filter(self, graphql_client):
        """Test querying features with bounding box filter."""
        # Create feature in San Francisco
        sf_feature = GeoJSONFeatureFactory(
            name="San Francisco Point", geometry=Point(-122.4194, 37.7749)
        )

        # Create feature in New York (outside bbox)
        GeoJSONFeatureFactory(name="New York Point", geometry=Point(-74.0060, 40.7128))

        # Query with bbox covering San Francisco Bay Area
        response = graphql_client(
            ALL_GEOJSON_FEATURES_QUERY, variables={"bbox": "-122.5,37.7,-122.3,37.8"}
        )
        content = response.json()

        # Should only return the San Francisco feature
        edges = content["data"]["allGeojsonFeatures"]["edges"]
        assert len(edges) == 1
        assert edges[0]["node"]["id"] == sf_feature.relay_id
        assert edges[0]["node"]["name"] == "San Francisco Point"

    def test_query_with_search_filter(self, graphql_client):
        """Test querying features with search filter."""
        feature = GeoJSONFeatureFactory(name="Golden Gate Bridge")
        GeoJSONFeatureFactory(name="Bay Bridge")

        response = graphql_client(ALL_GEOJSON_FEATURES_QUERY, variables={"q": "Golden"})
        content = response.json()

        edges = content["data"]["allGeojsonFeatures"]["edges"]
        assert len(edges) == 1
        assert edges[0]["node"]["id"] == feature.relay_id

    def test_query_with_ordering(self, graphql_client):
        """Test querying features with ordering."""
        GeoJSONFeatureFactory(name="Charlie")
        feature_alpha = GeoJSONFeatureFactory(name="Alpha")
        GeoJSONFeatureFactory(name="Bravo")

        response = graphql_client(ALL_GEOJSON_FEATURES_QUERY, variables={"orderBy": "name"})
        content = response.json()

        edges = content["data"]["allGeojsonFeatures"]["edges"]
        assert len(edges) == 3
        assert edges[0]["node"]["id"] == feature_alpha.relay_id

    def test_geojson_field_point(self, graphql_client):
        """Test that GeoJSON field correctly serializes Point geometry."""
        GeoJSONFeatureFactory(name="Test Point", geometry=Point(-122.4194, 37.7749))

        response = graphql_client(ALL_GEOJSON_FEATURES_QUERY)
        content = response.json()

        geojson = content["data"]["allGeojsonFeatures"]["edges"][0]["node"]["geojson"]
        assert geojson["type"] == "Point"
        assert geojson["coordinates"] == [-122.4194, 37.7749]

    def test_geojson_field_polygon(self, graphql_client):
        """Test that GeoJSON field correctly serializes Polygon geometry."""
        polygon = Polygon(
            (
                (-122.45, 37.75),
                (-122.40, 37.75),
                (-122.40, 37.80),
                (-122.45, 37.80),
                (-122.45, 37.75),
            )
        )

        GeoJSONFeatureFactory(name="Test Polygon", geometry=polygon)

        response = graphql_client(ALL_GEOJSON_FEATURES_QUERY)
        content = response.json()

        geojson = content["data"]["allGeojsonFeatures"]["edges"][0]["node"]["geojson"]
        assert geojson["type"] == "Polygon"
        assert len(geojson["coordinates"]) == 1  # One ring
        assert len(geojson["coordinates"][0]) == 5  # 5 points (closed)


class TestGeoJSONFeatureWithTargetQuery:
    """Test querying GeoJSON features with target field."""

    def test_feature_with_profile_target(self, graphql_client):
        """Test that target field correctly resolves to ProfileObjectType."""
        user = UserFactory(email="test@example.com")
        profile = ProfileFactory(owner=user, name="Test Profile")

        feature = GeoJSONFeatureFactory(
            name="Profile Location", geometry=Point(-122.4194, 37.7749), target=profile
        )

        response = graphql_client(
            GEOJSON_FEATURE_WITH_TARGET_QUERY, variables={"id": feature.relay_id}
        )
        content = response.json()

        # Debug output
        if "errors" in content:
            print("GraphQL Errors:", content["errors"])
            assert False, f"GraphQL query failed: {content['errors']}"

        node = content["data"]["node"]
        assert node["id"] == feature.relay_id
        assert node["name"] == "Profile Location"

        # Check that target is correctly resolved
        target = node["target"]
        assert target is not None
        assert target["__typename"] == "Profile"
        assert target["name"] == "Test Profile"
        # Verify owner relationship exists (email might be restricted by permissions)
        assert target["owner"] is not None
        assert target["owner"]["id"] == user.relay_id

    def test_feature_without_target(self, graphql_client):
        """Test feature without a target returns null for target field."""
        feature = GeoJSONFeatureFactory(
            name="No Target Feature", geometry=Point(-122.4194, 37.7749)
        )

        response = graphql_client(
            GEOJSON_FEATURE_WITH_TARGET_QUERY, variables={"id": feature.relay_id}
        )
        content = response.json()

        node = content["data"]["node"]
        assert node["id"] == feature.relay_id
        assert node["target"] is None

    def test_multiple_features_with_different_targets(self, graphql_client):
        """Test querying multiple features with different target types."""
        profile1 = ProfileFactory(name="Profile 1")
        profile2 = ProfileFactory(name="Profile 2")

        feature1 = GeoJSONFeatureFactory(
            name="Location 1", geometry=Point(-122.4194, 37.7749), target=profile1
        )

        feature2 = GeoJSONFeatureFactory(
            name="Location 2", geometry=Point(-122.2711, 37.8044), target=profile2
        )

        # Query first feature
        response1 = graphql_client(
            GEOJSON_FEATURE_WITH_TARGET_QUERY, variables={"id": feature1.relay_id}
        )
        content1 = response1.json()
        assert content1["data"]["node"]["target"]["name"] == "Profile 1"

        # Query second feature
        response2 = graphql_client(
            GEOJSON_FEATURE_WITH_TARGET_QUERY, variables={"id": feature2.relay_id}
        )
        content2 = response2.json()
        assert content2["data"]["node"]["target"]["name"] == "Profile 2"


class TestGeoJSONFeatureNodeQuery:
    """Test querying a single GeoJSON feature by ID."""

    def test_query_feature_by_id(self, graphql_client):
        """Test querying a single feature by relay ID."""
        feature = GeoJSONFeatureFactory(name="Single Feature", geometry=Point(-122.4194, 37.7749))

        response = graphql_client(GEOJSON_FEATURE_QUERY, variables={"id": feature.relay_id})
        content = response.json()

        node = content["data"]["geojsonFeature"]
        assert node["id"] == feature.relay_id
        assert node["name"] == "Single Feature"
        assert node["geojson"]["type"] == "Point"

    def test_query_feature_with_target(self, graphql_client):
        """Test querying feature can access its target through node query."""
        profile = ProfileFactory()
        feature = GeoJSONFeatureFactory(
            name="Feature with Target", geometry=Point(-122.4194, 37.7749), target=profile
        )

        # Use node query instead which properly exposes the target
        query = (
            """
            query {
                node(id: "%s") {
                    ... on GeoJSONFeatureObjectType {
                        id
                        name
                        target {
                            id
                        }
                    }
                }
            }
        """
            % feature.relay_id
        )

        response = graphql_client(query)
        content = response.json()

        node = content["data"]["node"]
        assert node["target"] is not None
        assert node["target"]["id"] == profile.relay_id


class TestEmptyResults:
    """Test queries with no results."""

    def test_query_all_with_no_features(self, graphql_client):
        """Test querying when no features exist."""
        response = graphql_client(ALL_GEOJSON_FEATURES_QUERY)
        content = response.json()

        assert len(content["data"]["allGeojsonFeatures"]["edges"]) == 0

    def test_query_with_bbox_no_results(self, graphql_client):
        """Test bbox filter with no matching features."""
        GeoJSONFeatureFactory(name="Far Away", geometry=Point(-74.0060, 40.7128))

        response = graphql_client(
            ALL_GEOJSON_FEATURES_QUERY, variables={"bbox": "-122.5,37.7,-122.3,37.8"}
        )
        content = response.json()

        assert len(content["data"]["allGeojsonFeatures"]["edges"]) == 0
