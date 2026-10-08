# BaseApp Geo

Reusable app that attaches GeoJSON features (Points and Polygons) to any model.

## How to install

```bash
pip install baseapp-backend
```

Requires PostGIS: the project database must use the
`django.contrib.gis.db.backends.postgis` engine, and `django.contrib.gis` must
be in `INSTALLED_APPS`.

Add `baseapp_geo` to `INSTALLED_APPS`. The package registers itself as a plugin
(see `baseapp.geo.plugin:GeoPlugin`), so:

- `GeoQueries` / `GeoMutations` are contributed via
  `plugin_registry.get_all_graphql_queries()` / `get_all_graphql_mutations()`.
- `GeoPermissionsBackend` is contributed via
  `plugin_registry.get("AUTHENTICATION_BACKENDS", "baseapp.geo")` and spliced
  into the project's `AUTHENTICATION_BACKENDS`.

```python
# settings.py
INSTALLED_APPS += [
    "django.contrib.gis",
    "baseapp.geo",
]
```

## Permissions

`GeoPermissionsBackend` grants:

- `view_geojsonfeature` — everyone, including anonymous users (public read).
- `add_geojsonfeature` — any authenticated user.

`change_geojsonfeature` / `delete_geojsonfeature` are not granted by this
backend; they fall through to Django's standard permission system (e.g.
superusers, or per-user/group permissions assigned by the project).

## How to use

### GraphQL — exposing the schema

Nothing to do. The plugin entry-point in `pyproject.toml` registers
`GeoQueries` and `GeoMutations`, and the project's root `Query` / `Mutation`
should already spread `*plugin_registry.get_all_graphql_queries()` and
`*plugin_registry.get_all_graphql_mutations()`. `geoFeature`, `geoFeatures`,
`geoFeatureCreate`, `geoFeatureUpdate`, and `geoFeatureDelete` show up
automatically.

### Querying features

`geoFeatures` is a Relay connection filtered by `GeoJSONFeatureFilter`:

| Filter | Format | Semantics |
| --- | --- | --- |
| `bbox` | `minLon,minLat,maxLon,maxLat` (WGS 84) | Features whose geometry **intersects** the box. Boxes crossing the antimeridian (`minLon > maxLon`, RFC 7946 §5.2) are split into two OR-ed boxes automatically. |
| `near` | `lng,lat,radiusMeters` | `ST_DWithin`: polygons match when their **nearest edge** is within the radius, not their centroid. Radius must satisfy `0 < r <= 100000` (100 km cap). |
| `featureType` | string | Exact match on the feature's type label. |
| `targetObjectId` | Relay global ID | Features attached to that object. |

```graphql
query {
  geoFeatures(bbox: "-74.3,40.5,-73.7,40.9", featureType: "store") {
    edges {
      node {
        id
        geometry { type coordinates }
        properties { name description featureType }
      }
    }
  }
}
```

Malformed filter values (wrong arity, out-of-range coordinates, radius over the
cap, unknown target IDs) raise field-scoped validation errors instead of
silently returning unfiltered results.

### Vector tiles (maps)

`geoFeatures` returns at most 100 features per page, which is too few to draw a
dense map. For maps, the plugin also serves features as
[Mapbox Vector Tiles](https://github.com/mapbox/vector-tile-spec) (MVT), built by
PostGIS (`ST_AsMVT`), through the project's `v1` REST URLs:

```
GET /v1/geo/tiles/{z}/{x}/{y}.mvt
```

- **From zoom 13 up**, the tile's `features` layer holds every feature in it,
  points as points and polygons as polygons, with `id` and `feature_type`
  attributes.
- **Below zoom 13**, the `clusters` layer aggregates features into a 16×16 grid
  per tile: one point per non-empty cell, at the centroid of its features, with
  a `point_count`. Each feature counts in exactly one tile, so totals add up.
- **Filters**: the same query parameters as `geoFeatures` (`feature_type`,
  `target_object_id`, `bbox`, `near`), e.g. `?feature_type=store`. Malformed
  values return `400` with field errors.
- **Access**: requires `view_geojsonfeature`, through `has_perm` (public with the
  default backend).
- **Responses**: empty tiles return `204`. Tiles carry
  `Cache-Control: public, max-age=300`, so a CDN can absorb map pans.

With MapLibre GL:

```js
map.addSource("features", {
  type: "vector",
  tiles: [`${API_URL}/v1/geo/tiles/{z}/{x}/{y}.mvt?feature_type=store`],
});
map.addLayer({
  id: "clusters",
  type: "circle",
  source: "features",
  "source-layer": "clusters",
  paint: { "circle-radius": ["interpolate", ["linear"], ["get", "point_count"], 1, 4, 100, 18] },
});
map.addLayer({ id: "features", type: "circle", source: "features", "source-layer": "features" });
```

To add attributes or filters, subclass the view and route it in your project:

```python
# myproject/geo/views.py
from django.db.models import F, Q
from baseapp.geo.rest_framework.views import GeoJSONFeatureTileView


class StoreTileView(GeoJSONFeatureTileView):
    cluster_max_zoom = 12  # individual features from zoom 12
    cluster_grid_size = 8  # fewer, larger clusters

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        if self.request.query_params.get("open_now") == "true":
            queryset = queryset.filter(Q(name__icontains="24h"))
        return queryset

    def get_feature_properties(self):
        # Values must be strings, numbers or booleans.
        return {**super().get_feature_properties(), "name": F("name")}
```

`baseapp.geo.tiles.build_features_tile` / `build_clusters_tile` build tiles from
any `GeoJSONFeature` queryset, for projects that need their own endpoint.

### Geometry input

Mutations accept geometry through the `Geometry` scalar as any of:

- a GeoJSON dict — `{"type": "Point", "coordinates": [10.0, 20.0]}`
- WKT / EWKT — `SRID=4326;POINT(10 20)`
- HEX(E)WKB

Prefer GeoJSON or EWKT with an explicit `SRID=4326;` prefix: plain WKT without
an SRID prefix is interpreted with the form widget's default SRID. Only `Point`
and `Polygon` geometry types are accepted; anything else returns a `geometry`
field error.

## How to customise the GeoJSONFeature model

Define a concrete model in your project that subclasses the abstract:

```python
# myproject/geo/models.py
from baseapp.geo.models import AbstractGeoJSONFeature


class GeoJSONFeature(AbstractGeoJSONFeature):
    class Meta(AbstractGeoJSONFeature.Meta):
        pass
```

Add the new app to `INSTALLED_APPS`, run `makemigrations` / `migrate`, and
point the swapper setting at it:

```python
# settings.py
BASEAPP_GEO_GEOJSONFEATURE_MODEL = "geo.GeoJSONFeature"
```

## Writing test cases in your project

`GeoJSONFeatureFactory` in `baseapp_geo.tests.factories` targets the swapped
model, so it works unchanged in consuming projects.

## How to develop

Clone the monorepo into your backend directory:

```bash
git clone git@github.com:silverlogic/baseapp-backend.git
```

Then install editable:

```bash
pip install -e baseapp-backend
```
