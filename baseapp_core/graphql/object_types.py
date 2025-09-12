import graphene
from django.db.models import QuerySet
from query_optimizer import DjangoObjectType as OptimizerDjangoObjectType
from query_optimizer.compiler import optimize_single
from query_optimizer.optimizer import QueryOptimizer
from query_optimizer.typing import PK, GQLInfo, Optional, TModel

from .connections import CountedConnection

# from graphene_django import DjangoObjectType as GrapheneDjangoObjectType


class DjangoObjectType(OptimizerDjangoObjectType):
    pk = graphene.Int(required=True)

    class Meta:
        abstract = True

    @classmethod
    def __init_subclass_with_meta__(cls, **kwargs):
        model = kwargs.get("model")

        # Make ObjectType's name be identical to the model's name
        if ("name" not in kwargs or kwargs["name"] is None) and model:
            kwargs["name"] = model.__name__

        # Make ObjectType's default connection class be CountedConnection
        if "connection_class" not in kwargs or kwargs["connection_class"] is None:
            kwargs["connection_class"] = CountedConnection

        super().__init_subclass_with_meta__(**kwargs)

    def resolve_pk(self, info):
        return self.pk

    @classmethod
    def pre_optimization_hook(
        cls, queryset: QuerySet[TModel], optimizer: QueryOptimizer
    ) -> QuerySet[TModel]:
        """A hook for modifying the optimizer results before optimization happens."""
        queryset = cls._add_annotation(queryset)
        return super().pre_optimization_hook(queryset, optimizer)

    @classmethod
    def get_queryset(cls, queryset: QuerySet[TModel], info: GQLInfo) -> QuerySet[TModel]:
        queryset = cls._add_annotation(queryset)
        return super().get_queryset(queryset, info)

    @classmethod
    def get_node(cls, info: GQLInfo, pk: PK) -> Optional[TModel]:
        queryset = cls._meta.model._default_manager.all()
        queryset = cls._add_annotation(queryset)
        maybe_instance = optimize_single(
            queryset, info, pk=pk, max_complexity=cls._meta.max_complexity
        )
        if maybe_instance is not None:  # pragma: no cover
            cls.run_instance_checks(maybe_instance, info)
        return maybe_instance

    @classmethod
    def _add_annotation(cls, queryset: QuerySet[TModel]) -> QuerySet[TModel]:
        from baseapp_core.hashids.strategies import (
            get_hashids_strategy_from_instance_or_cls,
        )

        strategy = get_hashids_strategy_from_instance_or_cls(cls._meta.model)
        queryset = strategy.queryset_annotator.annotate(cls._meta.model, queryset)
        return queryset
