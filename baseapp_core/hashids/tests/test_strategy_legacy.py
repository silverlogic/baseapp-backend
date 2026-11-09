
import pytest

from baseapp_core.hashids.strategies.legacy import (
    LegacyDRFResolverStrategy,
    LegacyGraphQLResolverStrategy,
    LegacyIdResolverStrategy,
    LegacyQuerysetAnnotatorStrategy,
)
from baseapp_core.hashids.utils import to_global_id
from testproject.testapp.models import DummyLegacyModel
from testproject.testapp.tests.factories import DummyLegacyModelFactory

from .helpers import strawberry_info


@pytest.mark.django_db
class TestLegacyIdResolverStrategy:
    @pytest.fixture
    def resolver(self) -> LegacyIdResolverStrategy:
        return LegacyIdResolverStrategy()

    def test_get_id_from_instance_returns_legacy_id(self, resolver) -> None:
        instance = DummyLegacyModelFactory()
        assert resolver.get_id_from_instance(instance) == instance.pk

    def test_resolve_id_calls_mapping(self, resolver) -> None:
        dummy_obj = DummyLegacyModelFactory()
        result = resolver.resolve_id(dummy_obj.pk, model_cls=type(dummy_obj))
        assert result.pk == dummy_obj.pk

    def test_resolve_id_returns_none_for_nonexistent_id(self, resolver) -> None:
        random_id = 99999999  # unlikely to exist
        with pytest.raises(DummyLegacyModel.DoesNotExist):
            resolver.resolve_id(str(random_id), model_cls=DummyLegacyModel)

    def test_resolve_id_raises_for_invalid_id(self, resolver) -> None:
        invalid_id = "not-an-int"
        with pytest.raises(ValueError):
            resolver.resolve_id(invalid_id, model_cls=DummyLegacyModel)


@pytest.mark.django_db
class TestLegacyGraphQLResolverStrategy:
    @pytest.fixture
    def resolver(self) -> LegacyGraphQLResolverStrategy:
        return LegacyGraphQLResolverStrategy(id_resolver=LegacyIdResolverStrategy())

    def test_to_global_id_uses_id_resolver(self, resolver: LegacyGraphQLResolverStrategy) -> None:
        dummy_instance = DummyLegacyModelFactory()
        result = resolver.to_global_id(dummy_instance, "DummyLegacyModel", dummy_instance.pk)
        assert result == to_global_id("DummyLegacyModel", dummy_instance.pk)

    def test_get_pk_from_global_id(self, resolver: LegacyGraphQLResolverStrategy) -> None:
        dummy_instance = DummyLegacyModelFactory()
        global_id = to_global_id("DummyLegacyModel", dummy_instance.pk)
        assert resolver.get_pk_from_global_id(global_id) == str(dummy_instance.pk)

    def test_get_instance_from_global_id(self, resolver: LegacyGraphQLResolverStrategy) -> None:
        dummy_instance = DummyLegacyModelFactory()
        info = strawberry_info(dummy_instance)

        global_id = to_global_id("DummyLegacyModel", dummy_instance.pk)
        assert resolver.get_instance_from_global_id(info, global_id) == dummy_instance

    def test_get_instance_from_global_id_with_get_node(
        self, resolver: LegacyGraphQLResolverStrategy
    ) -> None:
        dummy_instance = DummyLegacyModelFactory()
        info = strawberry_info(dummy_instance)

        global_id = to_global_id("DummyLegacyModel", dummy_instance.pk)
        assert (
            resolver.get_instance_from_global_id(info, global_id, get_node=True) == dummy_instance
        )


@pytest.mark.django_db
class TestLegacyQuerysetAnnotatorStrategy:
    def test_annotate_do_nothing(self) -> None:
        DummyLegacyModelFactory()
        strategy = LegacyQuerysetAnnotatorStrategy()
        queryset = DummyLegacyModel.objects.all()
        annotated_queryset = strategy.annotate(DummyLegacyModel, queryset)
        assert annotated_queryset == queryset
        assert annotated_queryset.query.annotations == queryset.query.annotations


@pytest.mark.django_db
class TestLegacyDRFResolverStrategy:
    @pytest.fixture
    def resolver(self) -> LegacyDRFResolverStrategy:
        return LegacyDRFResolverStrategy(id_resolver=LegacyIdResolverStrategy())

    def test_resolve_public_id_to_pk_returns_input(self, resolver) -> None:
        # legacy DRF resolver is a no-op and should return the input unchanged
        dummy = DummyLegacyModelFactory()
        assert resolver.resolve_public_id_to_pk(str(dummy.pk)) == str(dummy.pk)
