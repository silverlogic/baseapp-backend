import math

import pytest
import swapper
from django.contrib.gis.geos import Point, Polygon
from django.db.models import F, Value
from django.db.models.functions import Concat
from django.test import override_settings
from rest_framework.test import APIRequestFactory

from baseapp.geo.rest_framework.views import MVT_CONTENT_TYPE, GeoJSONFeatureTileView
from baseapp.geo.tiles import MAX_ZOOM, WEB_MERCATOR_MAX_LATITUDE, Tile

from .factories import POINT_NYC, GeoJSONFeatureFactory
from .mvt import decode

pytestmark = pytest.mark.django_db

GeoJSONFeature = swapper.load_model("baseapp_geo", "GeoJSONFeature")

FEATURES_ZOOM = 14  # >= GeoJSONFeatureTileView.cluster_max_zoom: individual features
CLUSTERS_ZOOM = 10  # < cluster_max_zoom: clusters


def tile_for(point: Point, z: int) -> Tile:
    """The XYZ tile containing `point` at zoom `z`."""
    lon, lat = point.x, point.y
    tiles = 2**z
    x = math.floor((lon + 180) / 360 * tiles)
    lat_rad = math.radians(lat)
    y = math.floor((1 - math.asinh(math.tan(lat_rad)) / math.pi) / 2 * tiles)
    return Tile(z, x, y)


def tile_url(tile: Tile, query: str = "") -> str:
    return f"/v1/geo/tiles/{tile.z}/{tile.x}/{tile.y}.mvt{query}"


def offset(point: Point, meters_east: float = 0, meters_north: float = 0) -> Point:
    """`point` moved by roughly the given meters (fine for tests at city scale)."""
    lat = point.y + meters_north / 111_320
    lon = point.x + meters_east / (111_320 * math.cos(math.radians(point.y)))
    return Point(lon, lat, srid=4326)


def inside(tile: Tile, x_share: float, y_share: float) -> Point:
    """A point at the given share of the tile's width (west to east) and height (south to north)."""
    west, south, east, north = tile.lonlat_bounds()
    return Point(west + (east - west) * x_share, south + (north - south) * y_share, srid=4326)


def get_tile(client, tile: Tile, query: str = "") -> dict:
    response = client.get(tile_url(tile, query))
    assert response.status_code == 200, response.content
    assert response["Content-Type"] == MVT_CONTENT_TYPE
    return decode(response.content)


class TestTile:
    def test_validity(self) -> None:
        assert Tile(0, 0, 0).is_valid
        assert Tile(3, 7, 7).is_valid
        assert not Tile(3, 8, 0).is_valid
        assert not Tile(3, 0, -1).is_valid
        assert not Tile(MAX_ZOOM + 1, 0, 0).is_valid

    def test_world_tile_bounds(self) -> None:
        west, south, east, north = Tile(0, 0, 0).lonlat_bounds()
        assert (west, east) == (-180.0, 180.0)
        assert south == pytest.approx(-WEB_MERCATOR_MAX_LATITUDE)
        assert north == pytest.approx(WEB_MERCATOR_MAX_LATITUDE)

    def test_prefilter_only_on_small_tiles(self) -> None:
        assert Tile(3, 2, 3).prefilter_polygon() is None
        polygon = tile_for(POINT_NYC, FEATURES_ZOOM).prefilter_polygon()
        assert polygon is not None and polygon.contains(POINT_NYC)


class TestFeaturesTile:
    def test_points_and_polygons_with_properties(self, client) -> None:
        point = GeoJSONFeatureFactory(geometry=POINT_NYC, feature_type="tree")
        square = Polygon.from_bbox(
            (POINT_NYC.x + 0.0005, POINT_NYC.y, POINT_NYC.x + 0.001, POINT_NYC.y + 0.0005)
        )
        square.srid = 4326
        polygon = GeoJSONFeatureFactory(geometry=square, feature_type="grove")

        layers = get_tile(client, tile_for(POINT_NYC, FEATURES_ZOOM))

        assert set(layers) == {"features"}
        features = {f["properties"]["id"]: f for f in layers["features"]["features"]}
        assert set(features) == {point.pk, polygon.pk}
        assert features[point.pk]["type"] == "Point"
        assert features[point.pk]["properties"]["feature_type"] == "tree"
        assert features[polygon.pk]["type"] == "Polygon"
        assert features[polygon.pk]["properties"]["feature_type"] == "grove"

    def test_features_outside_the_tile_are_left_out(self, client) -> None:
        GeoJSONFeatureFactory(geometry=POINT_NYC)
        far = GeoJSONFeatureFactory(geometry=offset(POINT_NYC, meters_east=50_000))

        layers = get_tile(client, tile_for(POINT_NYC, FEATURES_ZOOM))

        assert far.pk not in [f["properties"]["id"] for f in layers["features"]["features"]]

    def test_feature_properties_hook(self) -> None:
        class TileView(GeoJSONFeatureTileView):
            def get_feature_properties(self) -> dict:
                return {
                    **super().get_feature_properties(),
                    "label": Concat(F("feature_type"), Value("!")),
                }

        GeoJSONFeatureFactory(geometry=POINT_NYC, feature_type="tree")
        tile = tile_for(POINT_NYC, FEATURES_ZOOM)
        request = APIRequestFactory().get(tile_url(tile))

        response = TileView.as_view()(request, z=tile.z, x=tile.x, y=tile.y)

        [feature] = decode(response.content)["features"]["features"]
        assert feature["properties"]["label"] == "tree!"


class TestClustersTile:
    def test_nearby_features_are_aggregated(self, client) -> None:
        tile = tile_for(POINT_NYC, CLUSTERS_ZOOM)
        center = inside(tile, 0.5, 0.5)
        for meters in (0, 5, 10):
            GeoJSONFeatureFactory(geometry=offset(center, meters_east=meters))
        GeoJSONFeatureFactory(geometry=inside(tile, 0.1, 0.1))  # another grid cell

        layers = get_tile(client, tile)

        assert set(layers) == {"clusters"}
        counts = sorted(f["properties"]["point_count"] for f in layers["clusters"]["features"])
        assert counts == [1, 3]
        assert all(f["type"] == "Point" for f in layers["clusters"]["features"])

    def test_polygons_count_once(self, client) -> None:
        tile = tile_for(POINT_NYC, CLUSTERS_ZOOM)
        west, south = inside(tile, 0.4, 0.4).coords
        east, north = inside(tile, 0.6, 0.6).coords
        square = Polygon.from_bbox((west, south, east, north))
        square.srid = 4326
        GeoJSONFeatureFactory(geometry=square)

        layers = get_tile(client, tile)

        assert [f["properties"]["point_count"] for f in layers["clusters"]["features"]] == [1]

    def test_counts_add_up_across_tiles(self, client) -> None:
        # Exactly on the vertical edge shared by two tiles: counted in one of them only.
        zoom = 5
        right = tile_for(POINT_NYC, zoom)
        edge_lon = right.x / 2**zoom * 360 - 180
        GeoJSONFeatureFactory(geometry=Point(edge_lon, POINT_NYC.y, srid=4326))
        left = Tile(zoom, right.x - 1, right.y)

        total = 0
        for tile in (left, right):
            response = client.get(tile_url(tile))
            if response.status_code == 200:
                total += sum(
                    f["properties"]["point_count"]
                    for f in decode(response.content)["clusters"]["features"]
                )
        assert total == 1


class TestTileEndpoint:
    def test_empty_tile_is_no_content(self, client) -> None:
        response = client.get(tile_url(tile_for(POINT_NYC, FEATURES_ZOOM)))

        assert response.status_code == 204
        assert response.content == b""

    def test_out_of_range_tile_is_not_found(self, client) -> None:
        assert client.get("/v1/geo/tiles/3/8/0.mvt").status_code == 404

    def test_cache_headers(self, client) -> None:
        GeoJSONFeatureFactory(geometry=POINT_NYC)

        response = client.get(tile_url(tile_for(POINT_NYC, FEATURES_ZOOM)))

        assert response["Cache-Control"] == "public, max-age=300"

    def test_filters_are_the_graphql_ones(self, client) -> None:
        tree = GeoJSONFeatureFactory(geometry=POINT_NYC, feature_type="tree")
        GeoJSONFeatureFactory(geometry=offset(POINT_NYC, meters_east=20), feature_type="bench")

        layers = get_tile(client, tile_for(POINT_NYC, FEATURES_ZOOM), "?feature_type=tree")

        assert [f["properties"]["id"] for f in layers["features"]["features"]] == [tree.pk]

    def test_invalid_filter_is_a_bad_request_not_a_server_error(self, client) -> None:
        # The FilterSet raises django's ValidationError while the queryset is evaluated.
        response = client.get(tile_url(tile_for(POINT_NYC, FEATURES_ZOOM), "?near=0,0"))

        assert response.status_code == 400
        assert "near" in response.json()

    @override_settings(AUTHENTICATION_BACKENDS=["django.contrib.auth.backends.ModelBackend"])
    def test_view_permission_is_required(self, client) -> None:
        # Without GeoPermissionsBackend nobody has view_geojsonfeature: has_perm decides.
        GeoJSONFeatureFactory(geometry=POINT_NYC)

        response = client.get(tile_url(tile_for(POINT_NYC, FEATURES_ZOOM)))

        assert response.status_code in (401, 403)
