import pytest
import swapper

from baseapp_profiles.tests.factories import ProfileFactory

GeoJSONFeature = swapper.load_model("baseapp_maps", "GeoJSONFeature")

pytestmark = pytest.mark.django_db

GEOJSON_FEATURE_CREATE_GRAPHQL = """
    mutation GeoJSONFeatureCreateMutation($input: GeoJSONFeatureCreateInput!) {
        geojsonFeatureCreate(input: $input) {
            geojsonFeature {
                node {
                    id
                    name
                    geojson {
                        type
                        coordinates
                    }
                    target {
                        __typename
                        ... on Profile {
                            id
                        }
                    }
                }
            }
            errors {
                field
                messages
            }
            _debug {
                exceptions {
                    stack
                }
            }
        }
    }
"""


def test_anon_cant_create_geojson_feature(graphql_client):
    """Anonymous users should not be able to create GeoJSON features."""
    response = graphql_client(
        GEOJSON_FEATURE_CREATE_GRAPHQL,
        variables={
            "input": {
                "name": "Test Point",
                "geometry": {"type": "Point", "coordinates": [-122.4194, 37.7749]},
            }
        },
    )
    content = response.json()
    assert content["errors"][0]["message"] == "authentication required"
    assert GeoJSONFeature.objects.count() == 0


def test_user_can_create_geojson_feature_without_target(graphql_user_client, django_user_client):
    """Authenticated users should be able to create GeoJSON features without a target."""
    response = graphql_user_client(
        GEOJSON_FEATURE_CREATE_GRAPHQL,
        variables={
            "input": {
                "name": "Test Point",
                "geometry": {"type": "Point", "coordinates": [-122.4194, 37.7749]},
            }
        },
    )
    content = response.json()
    assert "errors" not in content

    feature = GeoJSONFeature.objects.get()
    assert feature.name == "Test Point"
    assert feature.geometry.geom_type == "Point"
    assert feature.user == django_user_client.user
    assert feature.target is None

    # Verify GraphQL response
    data = content["data"]["geojsonFeatureCreate"]["geojsonFeature"]["node"]
    assert data["name"] == "Test Point"
    assert data["geojson"]["type"] == "Point"
    assert data["geojson"]["coordinates"] == [-122.4194, 37.7749]
    assert data["target"] is None


def test_user_can_create_geojson_feature_with_target(graphql_user_client, django_user_client):
    """Authenticated users should be able to create GeoJSON features with a target."""
    profile = ProfileFactory()

    response = graphql_user_client(
        GEOJSON_FEATURE_CREATE_GRAPHQL,
        variables={
            "input": {
                "name": "Profile Location",
                "geometry": {"type": "Point", "coordinates": [-122.4194, 37.7749]},
                "targetObjectId": profile.relay_id,
            }
        },
    )
    content = response.json()
    assert "errors" not in content

    feature = GeoJSONFeature.objects.get()
    assert feature.name == "Profile Location"
    assert feature.user == django_user_client.user
    assert feature.target == profile

    # Verify GraphQL response
    data = content["data"]["geojsonFeatureCreate"]["geojsonFeature"]["node"]
    assert data["target"]["__typename"] == "Profile"


def test_user_can_create_polygon_feature(graphql_user_client):
    """Test creating a polygon GeoJSON feature."""
    response = graphql_user_client(
        GEOJSON_FEATURE_CREATE_GRAPHQL,
        variables={
            "input": {
                "name": "Test Polygon",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-122.4, 37.8],
                            [-122.4, 37.7],
                            [-122.5, 37.7],
                            [-122.5, 37.8],
                            [-122.4, 37.8],
                        ]
                    ],
                },
            }
        },
    )
    content = response.json()
    assert "errors" not in content

    feature = GeoJSONFeature.objects.get()
    assert feature.geometry.geom_type == "Polygon"

    # Verify GraphQL response
    data = content["data"]["geojsonFeatureCreate"]["geojsonFeature"]["node"]
    assert data["geojson"]["type"] == "Polygon"
    assert len(data["geojson"]["coordinates"]) == 1
    assert len(data["geojson"]["coordinates"][0]) == 5


def test_user_can_create_linestring_feature(graphql_user_client):
    """Test creating a LineString GeoJSON feature."""
    response = graphql_user_client(
        GEOJSON_FEATURE_CREATE_GRAPHQL,
        variables={
            "input": {
                "name": "Test Route",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [-122.4, 37.8],
                        [-122.45, 37.75],
                        [-122.5, 37.7],
                    ],
                },
            }
        },
    )
    content = response.json()
    assert "errors" not in content

    feature = GeoJSONFeature.objects.get()
    assert feature.geometry.geom_type == "LineString"

    # Verify GraphQL response
    data = content["data"]["geojsonFeatureCreate"]["geojsonFeature"]["node"]
    assert data["geojson"]["type"] == "LineString"
    assert len(data["geojson"]["coordinates"]) == 3


def test_create_with_invalid_geometry_type(graphql_user_client):
    """Test that invalid geometry type returns an error."""
    response = graphql_user_client(
        GEOJSON_FEATURE_CREATE_GRAPHQL,
        variables={
            "input": {
                "name": "Invalid Geometry",
                "geometry": {"type": "InvalidType", "coordinates": [0, 0]},
            }
        },
    )
    content = response.json()
    assert "errors" in content
    assert GeoJSONFeature.objects.count() == 0


def test_create_with_invalid_coordinates(graphql_user_client):
    """Test that invalid coordinates return an error."""
    response = graphql_user_client(
        GEOJSON_FEATURE_CREATE_GRAPHQL,
        variables={
            "input": {
                "name": "Invalid Coordinates",
                "geometry": {"type": "Point", "coordinates": "invalid"},
            }
        },
    )
    content = response.json()
    assert "errors" in content
    assert GeoJSONFeature.objects.count() == 0


def test_create_with_invalid_target(graphql_user_client):
    """Test that invalid target relay ID returns an error."""
    response = graphql_user_client(
        GEOJSON_FEATURE_CREATE_GRAPHQL,
        variables={
            "input": {
                "name": "Invalid Target",
                "geometry": {"type": "Point", "coordinates": [-122.4194, 37.7749]},
                "targetObjectId": "InvalidRelayID",
            }
        },
    )
    content = response.json()
    assert "errors" in content
    assert GeoJSONFeature.objects.count() == 0
