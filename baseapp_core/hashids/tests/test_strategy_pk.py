
import pytest

from baseapp_core.hashids.strategies.legacy import LegacyIdResolverStrategy
from baseapp_core.hashids.strategies.pk import (
    PkDRFResolverStrategy,
    PkGraphQLResolverStrategy,
)
from baseapp_core.hashids.strategies.public_id.id_resolver import (
    PublicIdResolverStrategy,
)
from baseapp_core.hashids.utils import to_global_id
from testproject.testapp.tests.factories import (
    DummyLegacyModelFactory,
    DummyPublicIdModelFactory,
)


@pytest.mark.django_db
class TestPkGraphQLResolverStrategy:
    @pytest.fixture
    def resolver(self) -> PkGraphQLResolverStrategy:
        return PkGraphQLResolverStrategy(id_resolver=LegacyIdResolverStrategy())

    def test_to_global_id_uses_id_resolver(self, resolver: PkGraphQLResolverStrategy) -> None:
        dummy_instance = DummyLegacyModelFactory()
        result = resolver.to_global_id(dummy_instance, "DummyLegacyModel", dummy_instance.pk)
        assert result == to_global_id("DummyLegacyModel", dummy_instance.pk)


@pytest.mark.django_db
class TestPkDRFResolverStrategy:
    @pytest.fixture
    def resolver(self) -> PkDRFResolverStrategy:
        return PkDRFResolverStrategy(id_resolver=PublicIdResolverStrategy())

    def test_resolve_public_id_to_pk_returns_object_id(self, resolver) -> None:
        dummy = DummyPublicIdModelFactory()
        result = resolver.resolve_public_id_to_pk(str(dummy.public_id), expected_model=type(dummy))
        assert result == dummy.pk

    def test_cant_resolve_invalid_public_id(self, resolver) -> None:
        invalid_public_id = "invalid-uuid"
        with pytest.raises(Exception):
            resolver.resolve_public_id_to_pk(
                invalid_public_id, expected_model=DummyPublicIdModelFactory._meta.model
            )

    def test_cant_resolve_public_id_of_different_model(self, resolver) -> None:
        dummy = DummyPublicIdModelFactory()
        with pytest.raises(Exception):
            resolver.resolve_public_id_to_pk(
                str(dummy.public_id), expected_model=DummyLegacyModelFactory._meta.model
            )
