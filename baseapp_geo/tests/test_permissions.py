import pytest
import swapper
from constance.test import override_config
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import AnonymousUser, Permission
from django.test import override_settings

from baseapp_core.tests.factories import UserFactory

from .factories import GeoJSONFeatureFactory

pytestmark = pytest.mark.django_db

GeoJSONFeature = swapper.load_model("baseapp_geo", "GeoJSONFeature")
app_label = GeoJSONFeature._meta.app_label

VIEW_PERM = f"{app_label}.view_geojsonfeature"
ADD_PERM = f"{app_label}.add_geojsonfeature"
CHANGE_PERM = f"{app_label}.change_geojsonfeature"
DELETE_PERM = f"{app_label}.delete_geojsonfeature"

NODE_QUERY = """
    query GeoFeature($id: ID!) {
        geoFeature(id: $id) {
            id
        }
    }
"""

HAS_PERM_QUERY = """
    query GeoFeature($id: ID!) {
        geoFeature(id: $id) {
            id
            canView: hasPerm(perm: "view")
            canAdd: hasPerm(perm: "add")
            canChange: hasPerm(perm: "change")
            canDelete: hasPerm(perm: "delete")
        }
    }
"""


class DenyAllBackend(BaseBackend):
    """Real backend that denies every permission, including view (for the get_node gate test)."""

    def has_perm(self, user_obj, perm, obj=None) -> bool:
        return False


def grant_model_perm(user, codename: str) -> None:
    perm = Permission.objects.get(content_type__app_label=app_label, codename=codename)
    user.user_permissions.add(perm)


class TestPermissionMatrix:
    """Design section 6 matrix, resolved through the real AUTHENTICATION_BACKENDS chain."""

    def test_view_allowed_for_anonymous(self):
        assert AnonymousUser().has_perm(VIEW_PERM) is True

    def test_view_allowed_for_authenticated(self):
        assert UserFactory().has_perm(VIEW_PERM) is True

    def test_view_allowed_for_model_perm_holder(self):
        user = UserFactory()
        grant_model_perm(user, "view_geojsonfeature")
        assert user.has_perm(VIEW_PERM) is True

    def test_add_denied_for_anonymous(self):
        assert AnonymousUser().has_perm(ADD_PERM) is False

    def test_add_allowed_for_authenticated(self):
        assert UserFactory().has_perm(ADD_PERM) is True

    @pytest.mark.parametrize("perm", [CHANGE_PERM, DELETE_PERM])
    def test_change_and_delete_denied_for_anonymous(self, perm):
        assert AnonymousUser().has_perm(perm) is False

    @pytest.mark.parametrize("perm", [CHANGE_PERM, DELETE_PERM])
    def test_change_and_delete_denied_for_authenticated_without_model_perm(self, perm):
        assert UserFactory().has_perm(perm) is False

    @pytest.mark.parametrize("codename", ["change_geojsonfeature", "delete_geojsonfeature"])
    def test_change_and_delete_allowed_via_model_backend_fallthrough(self, codename):
        user = UserFactory()
        grant_model_perm(user, codename)
        assert user.has_perm(f"{app_label}.{codename}") is True

    def test_model_perm_grant_does_not_leak_across_codenames(self):
        user = UserFactory()
        grant_model_perm(user, "change_geojsonfeature")
        assert user.has_perm(CHANGE_PERM) is True
        assert user.has_perm(DELETE_PERM) is False


# Node lookups below run with public-id logic disabled: the public-id resolver looks up the
# schema type by model class name ("GeoJSONFeature"), while NFR-7 pins the ObjectType name as
# "GeoJSONFeatureObjectType", so relay_id-based node queries only resolve via the legacy strategy.
class TestGetNodePermissionGate:
    @override_config(ENABLE_PUBLIC_ID_LOGIC=False)
    def test_get_node_returns_feature_when_view_granted(self, graphql_client):
        feature = GeoJSONFeatureFactory()

        response = graphql_client(NODE_QUERY, variables={"id": feature.relay_id})
        content = response.json()

        assert "errors" not in content
        assert content["data"]["geoFeature"]["id"] == feature.relay_id

    @override_config(ENABLE_PUBLIC_ID_LOGIC=False)
    @override_settings(
        AUTHENTICATION_BACKENDS=["baseapp_geo.tests.test_permissions.DenyAllBackend"]
    )
    def test_get_node_returns_none_when_view_perm_denied(self, graphql_client):
        feature = GeoJSONFeatureFactory()

        response = graphql_client(NODE_QUERY, variables={"id": feature.relay_id})
        content = response.json()

        assert "errors" not in content
        assert content["data"]["geoFeature"] is None


class TestHasPermInterfaceField:
    @override_config(ENABLE_PUBLIC_ID_LOGIC=False)
    def test_has_perm_resolves_for_anonymous(self, graphql_client):
        feature = GeoJSONFeatureFactory()

        response = graphql_client(HAS_PERM_QUERY, variables={"id": feature.relay_id})
        content = response.json()

        assert "errors" not in content
        assert content["data"]["geoFeature"] == {
            "id": feature.relay_id,
            "canView": True,
            "canAdd": False,
            "canChange": False,
            "canDelete": False,
        }

    @override_config(ENABLE_PUBLIC_ID_LOGIC=False)
    def test_has_perm_resolves_for_authenticated(self, graphql_user_client):
        feature = GeoJSONFeatureFactory()

        response = graphql_user_client(HAS_PERM_QUERY, variables={"id": feature.relay_id})
        content = response.json()

        assert "errors" not in content
        data = content["data"]["geoFeature"]
        assert data["canView"] is True
        assert data["canAdd"] is True
        assert data["canChange"] is False
        assert data["canDelete"] is False
