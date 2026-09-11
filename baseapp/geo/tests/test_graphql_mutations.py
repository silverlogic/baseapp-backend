import pytest
import swapper
from django.contrib.auth.models import Permission

from baseapp_core.tests.factories import UserFactory

from .factories import GeoJSONFeatureFactory, point_nyc

pytestmark = pytest.mark.django_db

GeoJSONFeature = swapper.load_model("baseapp_geo", "GeoJSONFeature")
app_label = GeoJSONFeature._meta.app_label

POINT_GEOJSON = {"type": "Point", "coordinates": [10.0, 20.0]}
POLYGON_GEOJSON = {
    "type": "Polygon",
    "coordinates": [[[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5], [-0.5, -0.5]]],
}
LINESTRING_GEOJSON = {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 1.0]]}

CREATE_MUTATION = """
    mutation GeoFeatureCreate($input: GeoJSONFeatureCreateInput!) {
        geoFeatureCreate(input: $input) {
            geoFeature {
                node {
                    id
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
                    }
                }
            }
            errors {
                field
                messages
            }
        }
    }
"""

UPDATE_MUTATION = """
    mutation GeoFeatureUpdate($input: GeoJSONFeatureUpdateInput!) {
        geoFeatureUpdate(input: $input) {
            geoFeature {
                id
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
            errors {
                field
                messages
            }
        }
    }
"""

DELETE_MUTATION = """
    mutation GeoFeatureDelete($input: GeoJSONFeatureDeleteInput!) {
        geoFeatureDelete(input: $input) {
            deletedId
            target {
                id
            }
            errors {
                field
                messages
            }
        }
    }
"""


def grant_model_perm(user, codename: str) -> None:
    perm = Permission.objects.get(content_type__app_label=app_label, codename=codename)
    user.user_permissions.add(perm)


class TestGeoFeatureCreate:
    """geoFeatureCreate: Edge payload, target attachment, geometry via variables (AC-9.1)."""

    def test_create_returns_edge_with_target_attached(
        self, django_user_client, graphql_user_client
    ):
        response = graphql_user_client(
            CREATE_MUTATION,
            variables={
                "input": {
                    "targetObjectId": django_user_client.user.relay_id,
                    "geometry": POINT_GEOJSON,
                    "name": "Meeting point",
                    "description": "Where we meet",
                    "featureType": "poi",
                }
            },
        )
        content = response.json()

        assert "errors" not in content
        node = content["data"]["geoFeatureCreate"]["geoFeature"]["node"]
        assert node["geometry"] == {"type": "Point", "coordinates": [10.0, 20.0]}
        assert node["properties"] == {
            "name": "Meeting point",
            "description": "Where we meet",
            "featureType": "poi",
            "target": {"id": django_user_client.user.relay_id},
        }

        feature = GeoJSONFeature.objects.get()
        assert node["id"] == feature.relay_id
        assert feature.target == django_user_client.user
        assert feature.geometry.srid == 4326
        assert (feature.geometry.x, feature.geometry.y) == pytest.approx((10.0, 20.0))

    def test_create_geometry_via_ewkt_string_variable(
        self, django_user_client, graphql_user_client
    ):
        """WKT input needs an explicit SRID prefix: a bare `POINT(30 40)` gets the form
        widget's srid and is transformed away from lng/lat; EWKT persists 4326 as-is."""
        response = graphql_user_client(
            CREATE_MUTATION,
            variables={
                "input": {
                    "targetObjectId": django_user_client.user.relay_id,
                    "geometry": "SRID=4326;POINT(30 40)",
                }
            },
        )
        content = response.json()

        assert "errors" not in content
        node = content["data"]["geoFeatureCreate"]["geoFeature"]["node"]
        assert node["geometry"]["coordinates"] == pytest.approx([30.0, 40.0])

        feature = GeoJSONFeature.objects.get()
        assert feature.geometry.srid == 4326
        assert (feature.geometry.x, feature.geometry.y) == pytest.approx((30.0, 40.0))

    def test_create_polygon_geometry(self, django_user_client, graphql_user_client):
        response = graphql_user_client(
            CREATE_MUTATION,
            variables={
                "input": {
                    "targetObjectId": django_user_client.user.relay_id,
                    "geometry": POLYGON_GEOJSON,
                }
            },
        )
        content = response.json()

        assert "errors" not in content
        node = content["data"]["geoFeatureCreate"]["geoFeature"]["node"]
        assert node["geometry"]["type"] == "Polygon"

        feature = GeoJSONFeature.objects.get()
        assert feature.geometry.geom_type == "Polygon"
        assert feature.geometry.extent == pytest.approx((-0.5, -0.5, 0.5, 0.5))

    def test_create_invalid_linestring_yields_form_errors_and_no_feature(
        self, django_user_client, graphql_user_client
    ):
        """AC-9.4: invalid geometry surfaces as payload errors and no feature row is
        written. Only the GeoJSONFeature rowcount is asserted: resolving the target
        idempotently creates its DocumentId row even when the form fails."""
        response = graphql_user_client(
            CREATE_MUTATION,
            variables={
                "input": {
                    "targetObjectId": django_user_client.user.relay_id,
                    "geometry": LINESTRING_GEOJSON,
                }
            },
        )
        content = response.json()

        payload = content["data"]["geoFeatureCreate"]
        assert payload["geoFeature"] is None
        assert payload["errors"][0]["field"] == "geometry"
        assert payload["errors"][0]["messages"] == ["Geometry must be a Point or a Polygon."]
        assert GeoJSONFeature.objects.count() == 0


class TestGeoFeatureUpdate:
    """geoFeatureUpdate: every mutable field, partial updates, invalid geometry (AC-9.2)."""

    def test_perm_granted_user_updates_every_mutable_field(
        self, django_user_client, graphql_user_client
    ):
        feature = GeoJSONFeatureFactory(name="Old name", description="Old description", poi=True)
        grant_model_perm(django_user_client.user, "change_geojsonfeature")

        response = graphql_user_client(
            UPDATE_MUTATION,
            variables={
                "input": {
                    "id": feature.relay_id,
                    "geometry": POINT_GEOJSON,
                    "name": "New name",
                    "description": "New description",
                    "featureType": "area",
                }
            },
        )
        content = response.json()

        assert "errors" not in content
        data = content["data"]["geoFeatureUpdate"]["geoFeature"]
        assert data["id"] == feature.relay_id
        assert data["geometry"] == {"type": "Point", "coordinates": [10.0, 20.0]}
        assert data["properties"] == {
            "name": "New name",
            "description": "New description",
            "featureType": "area",
        }

        feature.refresh_from_db()
        assert feature.name == "New name"
        assert feature.description == "New description"
        assert feature.feature_type == "area"
        assert feature.geometry.srid == 4326
        assert (feature.geometry.x, feature.geometry.y) == pytest.approx((10.0, 20.0))

    def test_partial_update_preserves_unspecified_fields(
        self, django_user_client, graphql_user_client
    ):
        feature = GeoJSONFeatureFactory(
            name="Old name", description="Keep me", geometry=point_nyc(), poi=True
        )
        grant_model_perm(django_user_client.user, "change_geojsonfeature")

        response = graphql_user_client(
            UPDATE_MUTATION,
            variables={"input": {"id": feature.relay_id, "name": "New name"}},
        )
        content = response.json()

        assert "errors" not in content
        feature.refresh_from_db()
        assert feature.name == "New name"
        assert feature.description == "Keep me"
        assert feature.feature_type == "poi"
        assert (feature.geometry.x, feature.geometry.y) == pytest.approx((-73.9857, 40.7484))

    def test_update_invalid_linestring_yields_form_errors_and_no_change(
        self, django_user_client, graphql_user_client
    ):
        feature = GeoJSONFeatureFactory(name="Untouched")
        grant_model_perm(django_user_client.user, "change_geojsonfeature")

        response = graphql_user_client(
            UPDATE_MUTATION,
            variables={"input": {"id": feature.relay_id, "geometry": LINESTRING_GEOJSON}},
        )
        content = response.json()

        payload = content["data"]["geoFeatureUpdate"]
        assert payload["geoFeature"] is None
        assert payload["errors"][0]["field"] == "geometry"

        feature.refresh_from_db()
        assert feature.name == "Untouched"
        assert feature.geometry.geom_type == "Point"


class TestGeoFeatureDelete:
    """geoFeatureDelete: deletedId + target payload, row removal (AC-9.3)."""

    def test_perm_granted_user_deletes_feature(self, django_user_client, graphql_user_client):
        feature = GeoJSONFeatureFactory(target=django_user_client.user)
        relay_id = feature.relay_id
        grant_model_perm(django_user_client.user, "delete_geojsonfeature")

        response = graphql_user_client(DELETE_MUTATION, variables={"input": {"id": relay_id}})
        content = response.json()

        assert "errors" not in content
        payload = content["data"]["geoFeatureDelete"]
        assert payload["deletedId"] == relay_id
        assert payload["target"] == {"id": django_user_client.user.relay_id}
        assert GeoJSONFeature.objects.count() == 0


class TestWritePermissions:
    """Write-permission matrix through real mutations (AC-9.5, AC-9.6, AC-10.3)."""

    def test_anonymous_create_denied_with_no_rows_written(self, graphql_client):
        user = UserFactory()

        response = graphql_client(
            CREATE_MUTATION,
            variables={"input": {"targetObjectId": user.relay_id, "geometry": POINT_GEOJSON}},
        )
        content = response.json()

        assert content["errors"][0]["extensions"]["code"] == "permission_required"
        assert content["data"]["geoFeatureCreate"] is None
        assert GeoJSONFeature.objects.count() == 0

    def test_anonymous_update_denied_and_feature_unchanged(self, graphql_client):
        feature = GeoJSONFeatureFactory(name="Untouched")

        response = graphql_client(
            UPDATE_MUTATION,
            variables={"input": {"id": feature.relay_id, "name": "Hacked"}},
        )
        content = response.json()

        assert content["errors"][0]["extensions"]["code"] == "permission_required"
        feature.refresh_from_db()
        assert feature.name == "Untouched"

    def test_anonymous_delete_denied_and_feature_kept(self, graphql_client):
        feature = GeoJSONFeatureFactory()

        response = graphql_client(DELETE_MUTATION, variables={"input": {"id": feature.relay_id}})
        content = response.json()

        assert content["errors"][0]["extensions"]["code"] == "permission_required"
        assert GeoJSONFeature.objects.count() == 1

    def test_authenticated_without_model_perm_cannot_update(self, graphql_user_client):
        feature = GeoJSONFeatureFactory(name="Untouched")

        response = graphql_user_client(
            UPDATE_MUTATION,
            variables={"input": {"id": feature.relay_id, "name": "Hacked"}},
        )
        content = response.json()

        assert content["errors"][0]["extensions"]["code"] == "permission_required"
        feature.refresh_from_db()
        assert feature.name == "Untouched"

    def test_authenticated_without_model_perm_cannot_delete(self, graphql_user_client):
        feature = GeoJSONFeatureFactory()

        response = graphql_user_client(
            DELETE_MUTATION, variables={"input": {"id": feature.relay_id}}
        )
        content = response.json()

        assert content["errors"][0]["extensions"]["code"] == "permission_required"
        assert GeoJSONFeature.objects.count() == 1
