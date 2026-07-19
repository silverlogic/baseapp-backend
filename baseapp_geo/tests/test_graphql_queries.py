import pytest
import swapper
from django.contrib.gis.geos import Point

from baseapp_core.models import DocumentId
from baseapp_core.tests.factories import UserFactory

from .factories import POINT_NYC, GeoJSONFeatureFactory, point_nyc, unit_square_polygon

pytestmark = pytest.mark.django_db

GeoJSONFeature = swapper.load_model("baseapp_geo", "GeoJSONFeature")

FEATURE_FRAGMENT = """
    id
    type
    bbox
    geometry {
        type
        coordinates
    }
    properties {
        name
        description
        featureType
        target {
            id
        }
        created
        modified
    }
"""

NODE_QUERY = f"""
    query GeoFeature($id: ID!) {{
        geoFeature(id: $id) {{
            {FEATURE_FRAGMENT}
        }}
    }}
"""

GENERIC_NODE_QUERY = """
    query Node($id: ID!) {
        node(id: $id) {
            id
            ... on GeoJSONFeature {
                type
                properties {
                    name
                }
            }
        }
    }
"""

CONNECTION_QUERY = """
    query GeoFeatures($first: Int, $bbox: String, $near: String) {
        geoFeatures(first: $first, bbox: $bbox, near: $near) {
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


class TestFeatureWireShape:
    """Design section 6 SDL: RFC 7946 Feature shape on the wire (AC-4.1)."""

    def test_point_feature_full_wire_shape(self, graphql_client):
        user = UserFactory()
        feature = GeoJSONFeatureFactory(
            target=user,
            geometry=point_nyc(),
            name="Empire State Building",
            description="Landmark",
            poi=True,
        )

        response = graphql_client(NODE_QUERY, variables={"id": feature.relay_id})
        content = response.json()

        assert "errors" not in content
        data = content["data"]["geoFeature"]
        assert data["id"] == feature.relay_id
        assert data["type"] == "Feature"
        assert data["geometry"]["type"] == "Point"
        # GeoJSON coordinate order is [lng, lat] (RFC 7946).
        assert data["geometry"]["coordinates"] == pytest.approx([POINT_NYC.x, POINT_NYC.y])
        assert data["bbox"] == pytest.approx([POINT_NYC.x, POINT_NYC.y, POINT_NYC.x, POINT_NYC.y])

        properties = data["properties"]
        assert properties["name"] == "Empire State Building"
        assert properties["description"] == "Landmark"
        assert properties["featureType"] == "poi"
        assert properties["target"] == {"id": user.relay_id}
        assert properties["created"] is not None
        assert properties["modified"] is not None

    def test_polygon_feature_geometry_and_bbox(self, graphql_client):
        feature = GeoJSONFeatureFactory(area=True)

        response = graphql_client(NODE_QUERY, variables={"id": feature.relay_id})
        content = response.json()

        assert "errors" not in content
        data = content["data"]["geoFeature"]
        assert data["geometry"]["type"] == "Polygon"
        # Polygon coordinates are a list of linear rings in [lng, lat] order.
        ring = data["geometry"]["coordinates"][0]
        assert ring[0] == pytest.approx([-0.5, -0.5])
        assert data["bbox"] == pytest.approx([-0.5, -0.5, 0.5, 0.5])

    def test_generic_node_query_routes_through_get_node(self, graphql_client):
        feature = GeoJSONFeatureFactory(name="Node routed")

        response = graphql_client(GENERIC_NODE_QUERY, variables={"id": feature.relay_id})
        content = response.json()

        assert "errors" not in content
        node = content["data"]["node"]
        assert node["id"] == feature.relay_id
        assert node["type"] == "Feature"
        assert node["properties"]["name"] == "Node routed"


class TestGeoFeaturesConnection:
    """geoFeatures connection: pagination, totalCount, max_limit cap (AC-5.*)."""

    def test_anonymous_first_n_and_total_count(self, graphql_client):
        GeoJSONFeatureFactory.create_batch(3, target=UserFactory())

        response = graphql_client(CONNECTION_QUERY, variables={"first": 2})
        content = response.json()

        assert "errors" not in content
        data = content["data"]["geoFeatures"]
        assert data["totalCount"] == 3
        assert len(data["edges"]) == 2

    def test_max_limit_caps_page_size_at_100(self, graphql_client):
        """max_limit=100 (AC-5.3): first > 100 is rejected outright, and an unbounded
        query is capped at 100 edges — the server never returns more than 100 rows."""
        user = UserFactory()
        target_document = DocumentId.get_or_create_for_object(user)
        GeoJSONFeature.objects.bulk_create(
            GeoJSONFeature(
                target_document=target_document,
                geometry=Point(0, 0, srid=4326),
                name=f"feature-{i}",
            )
            for i in range(101)
        )

        response = graphql_client(CONNECTION_QUERY, variables={"first": 200})
        content = response.json()

        assert content["data"]["geoFeatures"] is None
        assert "exceeds the `first` limit of 100" in content["errors"][0]["message"]

        # Explicit null: graphql_query's mutable `extra={}` default leaks the previous
        # call's variables, so omitting them here would silently resend first=200.
        response = graphql_client(CONNECTION_QUERY, variables={"first": None})
        content = response.json()

        assert "errors" not in content
        data = content["data"]["geoFeatures"]
        assert data["totalCount"] == 101
        assert len(data["edges"]) == 100

    def test_empty_string_bbox_is_treated_as_filter_absent(self, graphql_client):
        """FR-12 boundary: "" is in django-filter's EMPTY_VALUES, so the bbox filter is
        skipped entirely (no validation error, no filtering) rather than rejected."""
        GeoJSONFeatureFactory(geometry=point_nyc())
        GeoJSONFeatureFactory(geometry=unit_square_polygon())

        response = graphql_client(CONNECTION_QUERY, variables={"bbox": ""})
        content = response.json()

        assert "errors" not in content
        assert content["data"]["geoFeatures"]["totalCount"] == 2

    def test_anonymous_map_query_combining_bbox_and_near(self, graphql_client):
        """Absorbed POC smoke: bbox + near combined, anonymously (AC-4.1, AC-5.1)."""
        GeoJSONFeatureFactory(name="Empire State Building", geometry=point_nyc())
        GeoJSONFeatureFactory(name="Null Island")

        response = graphql_client(
            CONNECTION_QUERY,
            variables={"first": 10, "bbox": "-74.1,40.6,-73.7,40.9", "near": "-73.99,40.75,5000"},
        )
        content = response.json()

        assert "errors" not in content
        data = content["data"]["geoFeatures"]
        assert data["totalCount"] == 1
        assert len(data["edges"]) == 1

        node = data["edges"][0]["node"]
        assert node["type"] == "Feature"
        assert node["geometry"]["type"] == "Point"
        assert node["geometry"]["coordinates"] == pytest.approx([POINT_NYC.x, POINT_NYC.y])
        assert node["properties"]["name"] == "Empire State Building"
        assert node["properties"]["description"] == ""
        assert node["properties"]["featureType"] == ""
