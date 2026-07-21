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
(see `baseapp_geo.plugin:GeoPlugin`), so:

- `GeoQueries` / `GeoMutations` are contributed via
  `plugin_registry.get_all_graphql_queries()` / `get_all_graphql_mutations()`.
- `GeoPermissionsBackend` is contributed via
  `plugin_registry.get("AUTHENTICATION_BACKENDS", "baseapp_geo")` and spliced
  into the project's `AUTHENTICATION_BACKENDS`.

```python
# settings.py
INSTALLED_APPS += [
    "django.contrib.gis",
    "baseapp_geo",
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
from baseapp_geo.models import AbstractGeoJSONFeature


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
