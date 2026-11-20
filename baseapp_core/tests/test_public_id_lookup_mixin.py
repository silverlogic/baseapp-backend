import re
import uuid
from typing import Any

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db.models import QuerySet
from django.test import override_settings
from rest_framework import serializers, viewsets
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from baseapp_core.hashids.strategies import annotate_public_ids
from baseapp_core.rest_framework.fields import PublicIdField, PublicIdRelatedField
from baseapp_core.rest_framework.mixins import (
    PUBLIC_ID_LOOKUP_REGEX,
    PublicIdLookupMixin,
)
from baseapp_core.rest_framework.routers import DefaultRouter
from testproject.testapp.models import (
    DummyLegacyModel,
    DummyPublicIdChildModel,
    DummyPublicIdModel,
)
from testproject.testapp.tests.factories import (
    DummyLegacyModelFactory,
    DummyPublicIdChildModelFactory,
    DummyPublicIdModelFactory,
)

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()


class DummySerializer(serializers.ModelSerializer):
    id = PublicIdField()

    class Meta:
        model = DummyPublicIdModel
        fields = ("id", "name")


class DummyViewSet(PublicIdLookupMixin, viewsets.ReadOnlyModelViewSet):
    queryset = DummyPublicIdModel.objects.all()
    serializer_class = DummySerializer
    permission_classes = []
    authentication_classes = []
    pagination_class = None


class DummyStrictViewSet(DummyViewSet):
    allow_pk_lookup = False


class DummyOwnQuerysetViewSet(DummyViewSet):
    def get_queryset(self) -> QuerySet[DummyPublicIdModel]:
        return DummyPublicIdModel.objects.order_by("pk")


class DummyLegacyViewSet(PublicIdLookupMixin, viewsets.ReadOnlyModelViewSet):
    queryset = DummyLegacyModel.objects.all()
    serializer_class = type(
        "DummyLegacySerializer",
        (serializers.ModelSerializer,),
        {"Meta": type("Meta", (), {"model": DummyLegacyModel, "fields": ("id", "name")})},
    )
    permission_classes = []
    authentication_classes = []


class ChildSerializer(serializers.ModelSerializer):
    id = PublicIdField()
    parent = PublicIdRelatedField(queryset=DummyPublicIdModel.objects.all())
    previous = PublicIdRelatedField(
        queryset=DummyPublicIdChildModel.objects.all(), required=False, allow_null=True
    )
    previous_parent = PublicIdRelatedField(
        source="previous.parent", read_only=True, allow_null=True
    )

    class Meta:
        model = DummyPublicIdChildModel
        fields = ("id", "name", "parent", "previous", "previous_parent")


class ChildViewSet(PublicIdLookupMixin, viewsets.ModelViewSet):
    serializer_class = ChildSerializer
    permission_classes = []
    authentication_classes = []

    def get_queryset(self) -> QuerySet[DummyPublicIdChildModel]:
        return annotate_public_ids(
            DummyPublicIdChildModel.objects.select_related("parent"),
            "parent",
            "previous",
            "previous__parent",
        )


def retrieve(viewset_class: type[viewsets.GenericViewSet], lookup: Any) -> Response:
    view = viewset_class.as_view({"get": "retrieve"})
    return view(factory.get("/"), pk=str(lookup))


def list_view(viewset_class: type[viewsets.GenericViewSet]) -> Response:
    view = viewset_class.as_view({"get": "list"})
    return view(factory.get("/"))


class TestPublicIdLookupMixin:
    def test_retrieve_by_public_id(self) -> None:
        dummy = DummyPublicIdModelFactory()
        response = retrieve(DummyViewSet, dummy.public_id)
        assert response.status_code == 200
        assert response.data["id"] == str(dummy.public_id)

    def test_unknown_public_id_is_404(self) -> None:
        assert retrieve(DummyViewSet, uuid.uuid4()).status_code == 404

    def test_another_models_public_id_is_404(self) -> None:
        child = DummyPublicIdChildModelFactory()
        # A DummyPublicIdModel row with the child's pk, so a resolver that ignores the model
        # would return it.
        if not DummyPublicIdModel.objects.filter(pk=child.pk).exists():
            DummyPublicIdModelFactory(id=child.pk)
        assert retrieve(DummyViewSet, child.public_id).status_code == 404

    def test_pk_lookup_is_allowed_by_default(self) -> None:
        dummy = DummyPublicIdModelFactory()
        response = retrieve(DummyViewSet, dummy.pk)
        assert response.status_code == 200
        assert response.data["id"] == str(dummy.public_id)

    @override_settings(BASEAPP_PUBLIC_ID_ALLOW_PK_LOOKUP=False)
    def test_pk_lookup_is_404_when_disabled_by_setting(self) -> None:
        dummy = DummyPublicIdModelFactory()
        # A 404 marks the test transaction for rollback (ATOMIC_REQUESTS), so it goes last.
        assert retrieve(DummyViewSet, dummy.public_id).status_code == 200
        assert retrieve(DummyViewSet, dummy.pk).status_code == 404

    def test_pk_lookup_is_404_when_disabled_on_the_viewset(self) -> None:
        dummy = DummyPublicIdModelFactory()
        assert retrieve(DummyStrictViewSet, dummy.public_id).status_code == 200
        assert retrieve(DummyStrictViewSet, dummy.pk).status_code == 404

    @override_settings(BASEAPP_PUBLIC_ID_ALLOW_PK_LOOKUP=False)
    def test_models_without_public_ids_keep_pk_lookups(self) -> None:
        legacy = DummyLegacyModelFactory()
        assert retrieve(DummyLegacyViewSet, legacy.pk).status_code == 200

    @override_settings(ENABLE_PUBLIC_ID_LOGIC=False, BASEAPP_PUBLIC_ID_ALLOW_PK_LOOKUP=False)
    def test_pk_lookup_without_public_id_logic(self) -> None:
        dummy = DummyPublicIdModelFactory()
        response = retrieve(DummyViewSet, dummy.pk)
        assert response.status_code == 200
        assert response.data["id"] == dummy.pk

    def test_list_is_annotated(self, django_assert_num_queries) -> None:
        DummyPublicIdModelFactory.create_batch(3)
        # Warm the content type cache, so the count does not depend on test order.
        ContentType.objects.get_for_model(DummyPublicIdModel)
        for viewset_class in (DummyViewSet, DummyOwnQuerysetViewSet):
            with django_assert_num_queries(1):
                response = list_view(viewset_class)
            assert response.status_code == 200
            assert all(row["id"] for row in response.data)

    def test_router_emits_the_public_id_pattern(self) -> None:
        router = DefaultRouter()
        router.register("dummies", DummyViewSet, basename="dummies")
        detail = next(url for url in router.urls if url.name == "dummies-detail")
        public_id = str(uuid.uuid4())
        assert detail.pattern.match(f"dummies/{public_id}/") is not None
        assert detail.pattern.match(f"dummies/{public_id.upper()}/") is not None
        assert detail.pattern.match("dummies/12/") is not None
        assert detail.pattern.match("dummies/not-an-id/") is None

    def test_lookup_regex(self) -> None:
        pattern = re.compile(rf"^(?:{PUBLIC_ID_LOOKUP_REGEX})$")
        assert pattern.match(str(uuid.uuid4()))
        assert pattern.match("42")
        assert not pattern.match(str(uuid.uuid1()))
        assert not pattern.match("abc")


class TestPublicIdLookupMixinWrites:
    def patch(self, child: DummyPublicIdChildModel, data: dict) -> Response:
        view = ChildViewSet.as_view({"patch": "partial_update"})
        return view(factory.patch("/", data, format="json"), pk=str(child.public_id))

    def test_update_renders_the_new_relations(self) -> None:
        child = DummyPublicIdChildModelFactory(previous=DummyPublicIdChildModelFactory())
        new_parent = DummyPublicIdModelFactory()
        new_previous = DummyPublicIdChildModelFactory()

        response = self.patch(
            child,
            {"parent": str(new_parent.public_id), "previous": str(new_previous.public_id)},
        )

        assert response.status_code == 200, response.data
        child.refresh_from_db()
        assert child.parent == new_parent
        assert child.previous == new_previous
        assert response.data["id"] == str(child.public_id)
        assert response.data["parent"] == str(new_parent.public_id)
        assert response.data["previous"] == str(new_previous.public_id)
        assert response.data["previous_parent"] == str(new_previous.parent.public_id)

    def test_update_to_null(self) -> None:
        child = DummyPublicIdChildModelFactory(previous=DummyPublicIdChildModelFactory())

        response = self.patch(child, {"previous": None})

        assert response.status_code == 200, response.data
        assert response.data["previous"] is None
        assert response.data["previous_parent"] is None

    def test_update_of_other_fields_keeps_the_annotated_ids(self) -> None:
        child = DummyPublicIdChildModelFactory(previous=DummyPublicIdChildModelFactory())

        response = self.patch(child, {"name": "renamed"})

        assert response.status_code == 200, response.data
        assert response.data["name"] == "renamed"
        assert response.data["parent"] == str(child.parent.public_id)
        assert response.data["previous_parent"] == str(child.previous.parent.public_id)

    def test_retrieve_reads_the_annotations(self, django_assert_num_queries) -> None:
        child = DummyPublicIdChildModelFactory(previous=DummyPublicIdChildModelFactory())
        expected = {
            "id": str(child.public_id),
            "name": child.name,
            "parent": str(child.parent.public_id),
            "previous": str(child.previous.public_id),
            "previous_parent": str(child.previous.parent.public_id),
        }
        view = ChildViewSet.as_view({"get": "retrieve"})

        # 1 to resolve the public id in the URL and 1 for the row with its annotations.
        with django_assert_num_queries(2):
            response = view(factory.get("/"), pk=expected["id"])

        assert response.data == expected
