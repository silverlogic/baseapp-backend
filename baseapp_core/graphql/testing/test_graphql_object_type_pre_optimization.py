from unittest.mock import patch

import pytest
from django.db import models

from baseapp_core.graphql import DjangoObjectType
from testproject.testapp.models import DummyPublicIdModel


class DummyStrategyAnnotator:
    def get_annotations(self, model_cls):
        return {"id": models.Value("annotated_id", output_field=models.CharField())}


class DummyStrategy:
    queryset_annotator = DummyStrategyAnnotator()


def dummy_get_hashids_strategy_from_instance_or_cls(instance_or_cls):
    return DummyStrategy()


class DummyQueryOptimizer:
    def __init__(self, only_fields=None, model=None):
        self.only_fields = only_fields or []
        self.model = model or DummyPublicIdModel
        self.annotations = {}
        self.select_related = {}
        self.prefetch_related = {}


class DummyDjangoObjectType(DjangoObjectType):
    class Meta:
        model = DummyPublicIdModel


@pytest.mark.django_db
class TestDjangoObjectTypePreOptimizationHook:
    @patch(
        "baseapp_core.hashids.strategies.get_hashids_strategy_from_instance_or_cls",
        side_effect=dummy_get_hashids_strategy_from_instance_or_cls,
    )
    def test_pre_optimization_hook_sets_annotations_when_id_in_only_fields(self, mock_strategy):
        queryset = DummyPublicIdModel.objects.all()
        optimizer = DummyQueryOptimizer(only_fields=["id", "name"], model=DummyPublicIdModel)

        result = DummyDjangoObjectType.pre_optimization_hook(queryset, optimizer)

        # Should set annotations on optimizer
        assert "id" in optimizer.annotations
        assert optimizer.annotations["id"].value == "annotated_id"
        assert result == queryset

    @patch(
        "baseapp_core.hashids.strategies.get_hashids_strategy_from_instance_or_cls",
        side_effect=dummy_get_hashids_strategy_from_instance_or_cls,
    )
    def test_pre_optimization_hook_does_not_set_annotations_when_id_not_in_only_fields(
        self, mock_strategy
    ):
        queryset = DummyPublicIdModel.objects.all()
        optimizer = DummyQueryOptimizer(only_fields=["name"], model=DummyPublicIdModel)

        result = DummyDjangoObjectType.pre_optimization_hook(queryset, optimizer)

        # Should not set annotations on optimizer
        assert optimizer.annotations == {}
        assert result == queryset

    @patch(
        "baseapp_core.hashids.strategies.get_hashids_strategy_from_instance_or_cls",
        side_effect=dummy_get_hashids_strategy_from_instance_or_cls,
    )
    def test_pre_optimization_hook_recurses_related_optimizers(self, mock_strategy):
        queryset = DummyPublicIdModel.objects.all()
        parent_optimizer = DummyQueryOptimizer(only_fields=["id"], model=DummyPublicIdModel)
        child_optimizer = DummyQueryOptimizer(only_fields=["id"], model=DummyPublicIdModel)
        parent_optimizer.select_related["child"] = child_optimizer

        result = DummyDjangoObjectType.pre_optimization_hook(queryset, parent_optimizer)

        # Both parent and child should have annotations set
        assert "id" in parent_optimizer.annotations
        assert "id" in child_optimizer.annotations
        assert result == queryset

    @patch(
        "baseapp_core.hashids.strategies.get_hashids_strategy_from_instance_or_cls",
        side_effect=dummy_get_hashids_strategy_from_instance_or_cls,
    )
    def test_pre_optimization_hook_recurses_prefetch_related_optimizers(self, mock_strategy):
        queryset = DummyPublicIdModel.objects.all()
        parent_optimizer = DummyQueryOptimizer(only_fields=["id"], model=DummyPublicIdModel)
        child_optimizer = DummyQueryOptimizer(only_fields=["id"], model=DummyPublicIdModel)
        parent_optimizer.prefetch_related["child"] = child_optimizer

        result = DummyDjangoObjectType.pre_optimization_hook(queryset, parent_optimizer)

        # Both parent and child should have annotations set
        assert "id" in parent_optimizer.annotations
        assert "id" in child_optimizer.annotations
        assert result == queryset
