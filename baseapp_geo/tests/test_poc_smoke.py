import pytest
from django.contrib.gis.geos import Point

from .factories import GeoJSONFeatureFactory

pytestmark = pytest.mark.django_db

MAP_QUERY = """
    query {
        geoFeatures(first: 10, bbox: "-74.1,40.6,-73.7,40.9", near: "-73.99,40.75,5000") {
            totalCount
            edges {
                node {
                    type
                    geometry {
                        type
                        coordinates
                    }
                    properties {
                        name
                        description
                        featureType
                    }
                }
            }
        }
    }
"""


def test_anonymous_map_query_returns_features_within_bbox_and_near(graphql_client):
    GeoJSONFeatureFactory(
        name="Empire State Building",
        geometry=Point(-73.9857, 40.7484, srid=4326),
    )
    GeoJSONFeatureFactory(name="Null Island", geometry=Point(0, 0, srid=4326))

    response = graphql_client(MAP_QUERY)
    content = response.json()

    assert "errors" not in content
    data = content["data"]["geoFeatures"]
    assert data["totalCount"] == 1
    assert len(data["edges"]) == 1

    node = data["edges"][0]["node"]
    assert node["type"] == "Feature"
    assert node["geometry"]["type"] == "Point"
    assert node["geometry"]["coordinates"] == pytest.approx([-73.9857, 40.7484])
    assert node["properties"]["name"] == "Empire State Building"
    assert node["properties"]["description"] == ""
    assert node["properties"]["featureType"] == ""
