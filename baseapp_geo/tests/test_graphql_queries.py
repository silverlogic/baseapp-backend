import uuid

import pytest
import swapper
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from graphql_relay import to_global_id

from baseapp_core.models import DocumentId
from baseapp_core.tests.factories import UserFactory
from baseapp_geo.graphql.filters import GeoJSONFeatureFilter

from .factories import (
    POINT_NYC,
    GeoJSONFeatureFactory,
    antimeridian_east,
    antimeridian_west,
    point_east_of_origin,
    point_nyc,
    unit_square_polygon,
)

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

FILTERED_CONNECTION_QUERY = """
    query GeoFeaturesFiltered(
        $first: Int
        $after: String
        $featureType: String
        $targetObjectId: String
    ) {
        geoFeatures(
            first: $first
            after: $after
            featureType: $featureType
            targetObjectId: $targetObjectId
        ) {
            totalCount
            pageInfo {
                hasNextPage
                endCursor
            }
            edges {
                node {
                    properties {
                        name
                        featureType
                    }
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


class TestBboxFilter:
    """bbox filter: intersects semantics, antimeridian split, malformed input (FR-10, AC-6.*)."""

    def _names(self, data):
        return {edge["node"]["properties"]["name"] for edge in data["edges"]}

    def test_bbox_includes_inside_and_straddling_excludes_outside(self, graphql_client):
        """Intersects semantics (AC-6.1): a polygon straddling the bbox edge is included
        even though it is not fully within the box; features outside are excluded."""
        GeoJSONFeatureFactory(name="inside")  # Point at (0, 0)
        GeoJSONFeatureFactory(name="outside", geometry=point_nyc())
        # Unit square spans -0.5..0.5 and straddles the bbox's west edge at -0.2.
        GeoJSONFeatureFactory(name="straddling", geometry=unit_square_polygon())

        response = graphql_client(CONNECTION_QUERY, variables={"bbox": "-0.2,-0.2,1.0,0.2"})
        content = response.json()

        assert "errors" not in content
        data = content["data"]["geoFeatures"]
        assert data["totalCount"] == 2
        assert self._names(data) == {"inside", "straddling"}

    def test_bbox_crossing_antimeridian_matches_both_sides(self, graphql_client):
        """RFC 7946 section 5.2: west > east means the box crosses the antimeridian and is
        split into two OR-ed boxes; features on both sides match, (0, 0) does not."""
        GeoJSONFeatureFactory(name="east-side", geometry=antimeridian_east())  # (179.5, 0)
        GeoJSONFeatureFactory(name="west-side", geometry=antimeridian_west())  # (-179.5, 0)
        GeoJSONFeatureFactory(name="origin")  # Point at (0, 0)

        response = graphql_client(CONNECTION_QUERY, variables={"bbox": "179,-1,-179,1"})
        content = response.json()

        assert "errors" not in content
        data = content["data"]["geoFeatures"]
        assert data["totalCount"] == 2
        assert self._names(data) == {"east-side", "west-side"}

    @pytest.mark.parametrize(
        "bbox",
        [
            pytest.param("-10,-10,10", id="wrong-arity"),
            pytest.param("a,-10,10,10", id="non-numeric"),
            pytest.param("-181,-10,10,10", id="lon-out-of-range"),
            pytest.param("-10,-91,10,10", id="lat-out-of-range"),
            pytest.param("-10,10,10,-10", id="south-gt-north"),
        ],
    )
    def test_malformed_bbox_yields_errors_not_full_table(self, graphql_client, bbox):
        """FR-12 / AC-6.2: malformed bbox surfaces as GraphQL errors[] with
        data.geoFeatures null — never silently ignored into a full-table result."""
        GeoJSONFeatureFactory()

        response = graphql_client(CONNECTION_QUERY, variables={"bbox": bbox})
        content = response.json()

        assert content["errors"]
        assert content["data"]["geoFeatures"] is None


class TestNearFilter:
    """near filter: metric correctness, nearest-edge semantics, radius cap (FR-11, AC-7.*)."""

    def _total_count(self, graphql_client, near):
        response = graphql_client(CONNECTION_QUERY, variables={"near": near})
        content = response.json()
        assert "errors" not in content
        return content["data"]["geoFeatures"]["totalCount"]

    def test_near_metric_brackets_1113m_distance(self, graphql_client):
        """AC-7.5: 0.01 deg of longitude at the equator is ~1113 m, so a query point
        0.01 deg east of a feature at the origin matches with radius 1200 m but not
        1000 m — proving the radius is metric, not degree-based."""
        GeoJSONFeatureFactory(name="origin")  # Point at (0, 0)
        GeoJSONFeatureFactory(name="far-away", geometry=point_nyc())

        assert self._total_count(graphql_client, "0.01,0,1200") == 1
        assert self._total_count(graphql_client, "0.01,0,1000") == 0

    def test_near_polygon_matches_on_nearest_edge_not_centroid(self, graphql_client):
        """AC-7.4: ST_DWithin measures to the polygon's nearest edge. From (0.51, 0)
        the unit square's east edge (x=0.5) is ~1113 m away while its centroid is
        ~56 km away, so radius 1200 matches and radius 1000 does not."""
        GeoJSONFeatureFactory(name="square", geometry=unit_square_polygon())

        assert self._total_count(graphql_client, "0.51,0,1200") == 1
        assert self._total_count(graphql_client, "0.51,0,1000") == 0

    def test_near_radius_at_cap_is_accepted(self, graphql_client):
        """FR-11 boundary: radius exactly MAX_NEAR_RADIUS_METERS (100 km) is valid."""
        GeoJSONFeatureFactory(name="origin")

        assert self._total_count(graphql_client, "0,0,100000") == 1

    @pytest.mark.parametrize(
        "near",
        [
            pytest.param("0,0", id="wrong-arity"),
            pytest.param("a,0,100", id="non-numeric"),
            pytest.param("-181,0,100", id="lon-out-of-range"),
            pytest.param("0,-91,100", id="lat-out-of-range"),
            pytest.param("0,0,0", id="zero-radius"),
            pytest.param("0,0,-1", id="negative-radius"),
            pytest.param("0,0,100001", id="radius-above-cap"),
        ],
    )
    def test_malformed_or_capped_near_yields_errors_not_full_table(self, graphql_client, near):
        """FR-12 / AC-7.2 / AC-7.3: malformed near or radius above the 100 km cap
        surfaces as GraphQL errors[] with data.geoFeatures null."""
        GeoJSONFeatureFactory()

        response = graphql_client(CONNECTION_QUERY, variables={"near": near})
        content = response.json()

        assert content["errors"]
        assert content["data"]["geoFeatures"] is None


class TestCombinedFilters:
    """Filters compose with AND and with Relay pagination (FR-13, AC-8.*)."""

    def _names(self, data):
        return {edge["node"]["properties"]["name"] for edge in data["edges"]}

    def test_bbox_and_near_combine_with_and(self, graphql_client):
        """AC-8.1: a feature must satisfy BOTH bbox and near — matching only one
        of the two filters is not enough."""
        # bbox east edge at lon 0.005; near centered at (0.01, 0) with radius 1200 m.
        GeoJSONFeatureFactory(name="both")  # (0, 0): in bbox, 1113 m from near center
        # (0.02, 0): 1113 m from near center but east of the bbox.
        GeoJSONFeatureFactory(name="near-only", geometry=Point(0.02, 0, srid=4326))
        # (0, 0.05): in bbox but ~5.6 km from the near center.
        GeoJSONFeatureFactory(name="bbox-only", geometry=Point(0, 0.05, srid=4326))

        response = graphql_client(
            CONNECTION_QUERY,
            variables={"bbox": "-0.1,-0.1,0.005,0.1", "near": "0.01,0,1200"},
        )
        content = response.json()

        assert "errors" not in content
        data = content["data"]["geoFeatures"]
        assert data["totalCount"] == 1
        assert self._names(data) == {"both"}

    def test_pagination_with_first_after_over_filtered_set(self, graphql_client):
        """AC-8.2: `first`/`after` cursors paginate the FILTERED set — totalCount and
        pages cover only matching features, with no overlap between pages."""
        for name in ("poi-1", "poi-2", "poi-3"):
            GeoJSONFeatureFactory(name=name, poi=True)
        GeoJSONFeatureFactory(name="not-poi", area=True)

        response = graphql_client(
            FILTERED_CONNECTION_QUERY, variables={"featureType": "poi", "first": 2}
        )
        content = response.json()

        assert "errors" not in content
        page_one = content["data"]["geoFeatures"]
        assert page_one["totalCount"] == 3
        assert len(page_one["edges"]) == 2
        assert page_one["pageInfo"]["hasNextPage"] is True

        response = graphql_client(
            FILTERED_CONNECTION_QUERY,
            variables={
                "featureType": "poi",
                "first": 2,
                "after": page_one["pageInfo"]["endCursor"],
            },
        )
        content = response.json()

        assert "errors" not in content
        page_two = content["data"]["geoFeatures"]
        assert len(page_two["edges"]) == 1
        assert page_two["pageInfo"]["hasNextPage"] is False
        assert self._names(page_one) | self._names(page_two) == {"poi-1", "poi-2", "poi-3"}

    def test_feature_type_and_target_object_id_combine_with_and(self, graphql_client):
        """AC-8.3: featureType + targetObjectId narrow to one target's features of
        one type — same-target features of another type and same-type features of
        another target (a Profile) are both excluded."""
        user = UserFactory()
        GeoJSONFeatureFactory(name="user-poi", target=user, poi=True)
        GeoJSONFeatureFactory(name="user-area", target=user, area=True)
        GeoJSONFeatureFactory(name="profile-poi", profile_target=True, poi=True)

        response = graphql_client(
            FILTERED_CONNECTION_QUERY,
            variables={"featureType": "poi", "targetObjectId": user.relay_id},
        )
        content = response.json()

        assert "errors" not in content
        data = content["data"]["geoFeatures"]
        assert data["totalCount"] == 1
        assert self._names(data) == {"user-poi"}


class TestTargetObjectIdFilter:
    """targetObjectId accepts both relay ID forms `_resolve_target` supports (AC-8.4)."""

    def _query_names(self, graphql_client, target_object_id):
        response = graphql_client(
            FILTERED_CONNECTION_QUERY, variables={"targetObjectId": target_object_id}
        )
        content = response.json()
        assert "errors" not in content
        data = content["data"]["geoFeatures"]
        return {edge["node"]["properties"]["name"] for edge in data["edges"]}

    def test_target_filter_accepts_public_uuid_id(self, graphql_client):
        user = UserFactory()
        GeoJSONFeatureFactory(name="mine", target=user)
        GeoJSONFeatureFactory(name="other")

        public_id = str(DocumentId.get_or_create_for_object(user).public_id)

        assert self._query_names(graphql_client, public_id) == {"mine"}

    def test_target_filter_accepts_legacy_base64_relay_id(self, graphql_client):
        user = UserFactory()
        GeoJSONFeatureFactory(name="mine", target=user)
        GeoJSONFeatureFactory(name="other")

        legacy_id = to_global_id("User", user.pk)

        assert self._query_names(graphql_client, legacy_id) == {"mine"}

    @pytest.mark.parametrize(
        "target_object_id",
        [
            pytest.param("not-a-valid-relay-id", id="malformed"),
            pytest.param(str(uuid.uuid4()), id="unknown-uuid"),
        ],
    )
    def test_bad_target_id_yields_errors_not_full_table(self, graphql_client, target_object_id):
        GeoJSONFeatureFactory()

        response = graphql_client(
            FILTERED_CONNECTION_QUERY, variables={"targetObjectId": target_object_id}
        )
        content = response.json()

        assert content["errors"]
        assert content["data"]["geoFeatures"] is None


class TestFilterSetDRFReusability:
    """AC-8.4: the FilterSet works outside graphene — instantiated directly (as DRF's
    DjangoFilterBackend does) it filters a queryset with no GraphQL context at all."""

    def test_filterset_filters_queryset_outside_graphene(self):
        user = UserFactory()
        match = GeoJSONFeatureFactory(name="match", target=user, poi=True)
        GeoJSONFeatureFactory(name="wrong-type", target=user)  # feature_type ""
        GeoJSONFeatureFactory(name="too-far", target=user, poi=True, geometry=point_nyc())
        GeoJSONFeatureFactory(name="wrong-target", poi=True)

        public_id = str(DocumentId.get_or_create_for_object(user).public_id)
        filterset = GeoJSONFeatureFilter(
            data={
                "near": "0.01,0,1200",
                "feature_type": "poi",
                "target_object_id": public_id,
            },
            queryset=GeoJSONFeature.objects.all(),
        )

        assert list(filterset.qs) == [match]

    def test_filterset_raises_validation_error_outside_graphene(self):
        GeoJSONFeatureFactory()

        filterset = GeoJSONFeatureFilter(
            data={"near": "0,0"}, queryset=GeoJSONFeature.objects.all()
        )

        with pytest.raises(ValidationError):
            filterset.qs

    def test_target_filter_east_point_distance_sanity(self):
        """Anchor for the 1113 m constant: the factory's east-of-origin point really
        is between 1000 and 1200 m from the origin on the geography column."""
        GeoJSONFeatureFactory(geometry=point_east_of_origin())

        included = GeoJSONFeatureFilter(
            data={"near": "0,0,1200"}, queryset=GeoJSONFeature.objects.all()
        )
        excluded = GeoJSONFeatureFilter(
            data={"near": "0,0,1000"}, queryset=GeoJSONFeature.objects.all()
        )

        assert included.qs.count() == 1
        assert excluded.qs.count() == 0
