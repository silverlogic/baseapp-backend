"""Mapbox Vector Tiles (MVT) of GeoJSON features, built by PostGIS.

Tiles follow the Web Mercator (EPSG:3857) XYZ scheme used by MapLibre and Mapbox. A tile holds
either every feature in its area (`build_features_tile`) or, for zoomed-out views, features
aggregated into grid clusters with a `point_count` (`build_clusters_tile`), so a map can show the
full picture of thousands of features at every zoom level.

Features come from a regular queryset, so callers filter them with the ORM; extra MVT
attributes are ORM expressions annotated on it.
"""

import math
from dataclasses import dataclass

from django.contrib.gis.geos import Polygon
from django.db import connection
from django.db.models import Expression, F, QuerySet

# Half the Web Mercator world width, in meters (EPSG:3857 bounds are ±this on both axes).
WEB_MERCATOR_HALF_WORLD = 20037508.342789244
# Web Mercator stops short of the poles.
WEB_MERCATOR_MAX_LATITUDE = 85.0511287798066

MAX_ZOOM = 24
# Below this zoom the geography prefilter is skipped: its great-circle edges diverge too much
# from the tile's straight Mercator edges on tiles this large.
PREFILTER_MIN_ZOOM = 4
# The geography prefilter envelope is grown by this share of the tile on every side, so
# features near an edge still reach the exact planar test.
PREFILTER_PADDING = 0.1

DEFAULT_EXTENT = 4096
DEFAULT_BUFFER = 64

GEOMETRY_ALIAS = "_mvt_geometry"


@dataclass(frozen=True)
class Tile:
    z: int
    x: int
    y: int

    @property
    def is_valid(self) -> bool:
        return 0 <= self.z <= MAX_ZOOM and 0 <= self.x < 2**self.z and 0 <= self.y < 2**self.z

    @property
    def size_meters(self) -> float:
        """Width (and height) of the tile in Web Mercator meters."""
        return 2 * WEB_MERCATOR_HALF_WORLD / 2**self.z

    def mercator_bounds(self) -> tuple[float, float, float, float]:
        """`(xmin, ymin, xmax, ymax)` in Web Mercator meters."""
        xmin = -WEB_MERCATOR_HALF_WORLD + self.x * self.size_meters
        ymax = WEB_MERCATOR_HALF_WORLD - self.y * self.size_meters
        return xmin, ymax - self.size_meters, xmin + self.size_meters, ymax

    def lonlat_bounds(self, padding: float = 0.0) -> tuple[float, float, float, float]:
        """`(west, south, east, north)` in WGS 84, grown by `padding` tiles on every side."""
        tiles = 2**self.z

        def longitude(x: float) -> float:
            return max(-180.0, min(180.0, x / tiles * 360.0 - 180.0))

        def latitude(y: float) -> float:
            lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / tiles))))
            return max(-WEB_MERCATOR_MAX_LATITUDE, min(WEB_MERCATOR_MAX_LATITUDE, lat))

        return (
            longitude(self.x - padding),
            latitude(self.y + 1 + padding),
            longitude(self.x + 1 + padding),
            latitude(self.y - padding),
        )

    def prefilter_polygon(self) -> Polygon | None:
        """Padded WGS 84 envelope for an index-backed geography prefilter, or None when the tile
        is too large for one to be safe (see `PREFILTER_MIN_ZOOM`)."""
        if self.z < PREFILTER_MIN_ZOOM:
            return None
        polygon = Polygon.from_bbox(self.lonlat_bounds(PREFILTER_PADDING))
        polygon.srid = 4326
        return polygon


def _quote(name: str) -> str:
    return connection.ops.quote_name(name)


def _property_alias(index: int) -> str:
    # Internal names: Django rejects annotations named like model fields (e.g. "id").
    return f"_mvt_property_{index}"


def _features_sql(
    queryset: QuerySet, geometry_field: str, properties: dict[str, Expression]
) -> tuple[str, tuple]:
    """SQL selecting each feature's geometry (aliased `GEOMETRY_ALIAS`) and its properties
    (aliased by `_property_alias`, in order)."""
    aliased = {
        _property_alias(index): expression for index, expression in enumerate(properties.values())
    }
    rows = queryset.order_by().values(**{GEOMETRY_ALIAS: F(geometry_field)}, **aliased)
    sql, params = rows.query.sql_with_params()
    return sql, tuple(params)


def _envelope_sql(tile: Tile) -> str:
    # z/x/y are validated integers, safe to inline.
    return f"ST_TileEnvelope({int(tile.z)}, {int(tile.x)}, {int(tile.y)})"


def _execute(sql: str, params: tuple) -> bytes:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
    return bytes(row[0]) if row and row[0] is not None else b""


def build_features_tile(
    tile: Tile,
    queryset: QuerySet,
    *,
    geometry_field: str = "geometry",
    properties: dict[str, Expression] | None = None,
    layer: str = "features",
    extent: int = DEFAULT_EXTENT,
    buffer: int = DEFAULT_BUFFER,
) -> bytes:
    """An MVT with one `layer` holding every feature of `queryset` in `tile`.

    Points stay points and polygons stay polygons (clipped to the tile plus `buffer`). Each
    feature carries the `properties` (name → ORM expression) as MVT attributes; their values
    must be strings, numbers or booleans. Returns `b""` when the tile is empty.
    """
    properties = properties or {}
    features_sql, params = _features_sql(queryset, geometry_field, properties)
    envelope = _envelope_sql(tile)
    aliases = [_property_alias(index) for index in range(len(properties))]
    inner_columns = "".join(f", f.{_quote(alias)}" for alias in aliases)
    named_columns = "".join(
        f", f.{_quote(alias)} AS {_quote(name)}" for alias, name in zip(aliases, properties)
    )
    sql = f"""
        WITH features AS ({features_sql}),
        projected AS (
            SELECT
                ST_Transform(f.{_quote(GEOMETRY_ALIAS)}::geometry, 3857) AS mercator{inner_columns}
            FROM features f
        )
        SELECT ST_AsMVT(tile, %s, %s, 'geom') FROM (
            SELECT ST_AsMVTGeom(f.mercator, {envelope}, %s, %s, true) AS geom{named_columns}
            FROM projected f
            WHERE f.mercator && {envelope}
        ) tile
        WHERE tile.geom IS NOT NULL
    """
    return _execute(sql, (*params, layer, extent, extent, buffer))


def build_clusters_tile(
    tile: Tile,
    queryset: QuerySet,
    *,
    geometry_field: str = "geometry",
    grid_size: int = 16,
    layer: str = "clusters",
    extent: int = DEFAULT_EXTENT,
) -> bytes:
    """An MVT with one `layer` of cluster points aggregating `queryset`'s features in `tile`.

    The tile is split into a `grid_size` × `grid_size` grid; each non-empty cell becomes a point
    at the centroid of its features, with a `point_count` attribute. Polygons count by their
    point on surface. Each feature is counted in exactly one tile (bounds are half-open), so
    counts add up across tiles. Returns `b""` when the tile is empty.
    """
    features_sql, params = _features_sql(queryset, geometry_field, {})
    envelope = _envelope_sql(tile)
    xmin, ymin, xmax, ymax = tile.mercator_bounds()
    cell = tile.size_meters / grid_size
    sql = f"""
        WITH features AS ({features_sql}),
        points AS (
            SELECT
                ST_Transform(ST_PointOnSurface(f.{_quote(GEOMETRY_ALIAS)}::geometry), 3857) AS p
            FROM features f
        ),
        in_tile AS (
            SELECT p FROM points
            WHERE ST_X(p) >= %s AND ST_X(p) < %s AND ST_Y(p) > %s AND ST_Y(p) <= %s
        )
        SELECT ST_AsMVT(tile, %s, %s, 'geom') FROM (
            SELECT
                ST_AsMVTGeom(ST_Centroid(ST_Collect(p)), {envelope}, %s, 0, true) AS geom,
                count(*)::integer AS point_count
            FROM in_tile
            GROUP BY floor((ST_X(p) - %s) / %s), floor((ST_Y(p) - %s) / %s)
        ) tile
        WHERE tile.geom IS NOT NULL
    """
    return _execute(
        sql,
        (*params, xmin, xmax, ymin, ymax, layer, extent, extent, xmin, cell, ymin, cell),
    )
