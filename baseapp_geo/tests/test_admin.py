import pytest
import swapper
from django.urls import reverse

from baseapp_core.models import DocumentId
from baseapp_core.tests.factories import UserFactory

from .factories import GeoJSONFeatureFactory

pytestmark = pytest.mark.django_db

GeoJSONFeatureModel = swapper.load_model("baseapp_geo", "GeoJSONFeature")

CHANGELIST_URL = reverse("admin:geo_geojsonfeature_changelist")
ADD_URL = reverse("admin:geo_geojsonfeature_add")

# Admin geometry input MUST carry an explicit SRID (EWKT): the form widget assigns
# its map srid (3857) to srid-less values -- including GeoJSON without a crs member --
# and transforms them, mangling the coordinates.
POINT_NYC_EWKT = "SRID=4326;POINT (-73.9857 40.7484)"
POINT_EWKT = "SRID=4326;POINT (10 20)"
LINESTRING_EWKT = "SRID=4326;LINESTRING (0 0, 1 1)"


@pytest.fixture
def superuser_client(django_client):
    user = UserFactory(is_staff=True, is_superuser=True)
    django_client.force_login(user)
    return django_client


def form_data(feature, **overrides):
    data = {
        "name": feature.name,
        "description": feature.description,
        "feature_type": feature.feature_type,
        "geometry": feature.geometry.ewkt,
        "target_document": str(feature.target_document_id),
    }
    data.update(overrides)
    return data


def test_changelist_renders_with_geometry_type_column(superuser_client):
    GeoJSONFeatureFactory(name="Empire State Building", poi=True)
    GeoJSONFeatureFactory(name="Unit Square Park", area=True)

    response = superuser_client.get(CHANGELIST_URL)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Empire State Building" in content
    assert "Unit Square Park" in content
    assert '<td class="field-geometry_type">Point</td>' in content
    assert '<td class="field-geometry_type">Polygon</td>' in content


def test_changelist_search_filters_by_name(superuser_client):
    GeoJSONFeatureFactory(name="Empire State Building")
    GeoJSONFeatureFactory(name="Null Island")

    response = superuser_client.get(CHANGELIST_URL, {"q": "Empire"})

    assert response.status_code == 200
    result_names = [obj.name for obj in response.context["cl"].result_list]
    assert result_names == ["Empire State Building"]


def test_add_with_valid_ewkt_point_succeeds(superuser_client):
    document = DocumentId.get_or_create_for_object(UserFactory())

    response = superuser_client.post(
        ADD_URL,
        {
            "name": "Added via admin",
            "description": "",
            "feature_type": "poi",
            "geometry": POINT_NYC_EWKT,
            "target_document": str(document.pk),
        },
    )

    assert response.status_code == 302
    feature = GeoJSONFeatureModel.objects.get(name="Added via admin")
    assert feature.geometry.geom_type == "Point"
    assert list(feature.geometry.coords) == pytest.approx([-73.9857, 40.7484])
    assert feature.target_document_id == document.pk


def test_change_with_valid_ewkt_point_succeeds(superuser_client):
    feature = GeoJSONFeatureFactory(name="Before change")
    change_url = reverse("admin:geo_geojsonfeature_change", args=[feature.pk])

    response = superuser_client.post(
        change_url,
        form_data(feature, name="After change", geometry=POINT_EWKT),
    )

    assert response.status_code == 302
    feature.refresh_from_db()
    assert feature.name == "After change"
    assert feature.geometry.geom_type == "Point"
    assert list(feature.geometry.coords) == pytest.approx([10.0, 20.0])


def test_add_with_linestring_shows_form_error(superuser_client):
    document = DocumentId.get_or_create_for_object(UserFactory())

    response = superuser_client.post(
        ADD_URL,
        {
            "name": "Bad geometry",
            "description": "",
            "feature_type": "",
            "geometry": LINESTRING_EWKT,
            "target_document": str(document.pk),
        },
    )

    assert response.status_code == 200
    errors = response.context["adminform"].form.errors
    assert "Geometry must be a Point or a Polygon." in errors["geometry"]
    assert not GeoJSONFeatureModel.objects.filter(name="Bad geometry").exists()
