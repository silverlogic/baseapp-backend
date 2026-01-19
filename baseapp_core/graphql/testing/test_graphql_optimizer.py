from unittest.mock import MagicMock, patch

import pytest
from django.db.models import QuerySet
from query_optimizer.typing import GQLInfo

from baseapp_core.graphql.optimizer import safe_optimize
from testproject.testapp.models import DummyLegacyModel
from testproject.testapp.tests.factories import (
    DummyLegacyModelFactory,
    DummyPublicIdModelFactory,
)


@pytest.mark.django_db
class TestSafeOptimize:
    @pytest.fixture
    def mock_info(self):
        info = MagicMock(spec=GQLInfo)
        return info

    @pytest.fixture
    def root_instance(self):
        return DummyLegacyModelFactory()

    @pytest.fixture
    def queryset(self):
        DummyLegacyModelFactory.create_batch(3)
        return DummyLegacyModel.objects.all()

    def test_safe_optimize_same_class_returns_queryset(self, mock_info, root_instance, queryset):
        result = safe_optimize(root_instance, mock_info, queryset)

        assert result == queryset
        assert isinstance(result, QuerySet)

    def test_safe_optimize_different_class_with_evaluate_true(self, mock_info, queryset):
        different_root = DummyPublicIdModelFactory()

        with patch("baseapp_core.graphql.optimizer.optimize") as mock_optimize:
            mock_optimize.return_value = queryset

            result = safe_optimize(different_root, mock_info, queryset, evaluate=True)

            mock_optimize.assert_called_once_with(queryset, mock_info, max_complexity=None)
            assert result == queryset

    def test_safe_optimize_different_class_with_evaluate_false(self, mock_info, queryset):
        different_root = DummyPublicIdModelFactory()

        with patch("baseapp_core.graphql.optimizer.optimize_without_evaluation") as mock_optimize:
            mock_optimize.return_value = queryset

            result = safe_optimize(different_root, mock_info, queryset, evaluate=False)

            mock_optimize.assert_called_once_with(queryset, mock_info, max_complexity=None)
            assert result == queryset

    def test_safe_optimize_with_max_complexity(self, mock_info, queryset):
        different_root = DummyPublicIdModelFactory()
        max_complexity = 50

        with patch("baseapp_core.graphql.optimizer.optimize") as mock_optimize:
            mock_optimize.return_value = queryset

            result = safe_optimize(
                different_root, mock_info, queryset, max_complexity=max_complexity
            )

            mock_optimize.assert_called_once_with(
                queryset, mock_info, max_complexity=max_complexity
            )
            assert result == queryset
