from typing import Any

import graphene
from django.db.models import QuerySet
from query_optimizer import DjangoObjectType as OptimizerDjangoObjectType
from query_optimizer.optimizer import QueryOptimizer
from query_optimizer.typing import TModel

from .connections import CountedConnection


class DjangoObjectType(OptimizerDjangoObjectType):
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

    @classmethod
    def pre_optimization_hook(
        cls, queryset: QuerySet[TModel], optimizer: QueryOptimizer
    ) -> QuerySet[TModel]:
        """
        A hook for modifying the optimizer results before optimization happens.
        Recursively sets annotations for optimizer and its related optimizers.
        Also checks only_fields to avoid unnecessary annotations.
        """

        def recursive_set_annotations(opt: QueryOptimizer, model_cls: TModel):
            # Only add the annotations if the id field is in the only_fields
            only_fields_set = set(opt.only_fields)
            if "id" in only_fields_set:
                new_ann = cls._get_annotations(model_cls)
                opt.annotations = {**(opt.annotations or {}), **new_ann}

            for related_opt in opt.select_related.values():
                recursive_set_annotations(related_opt, related_opt.model)

            for related_opt in opt.prefetch_related.values():
                recursive_set_annotations(related_opt, related_opt.model)

        recursive_set_annotations(optimizer, queryset.model)

        return super().pre_optimization_hook(queryset, optimizer)

    @classmethod
    def _get_annotations(cls, model_cls: TModel) -> dict[str, Any]:
        from baseapp_core.hashids.strategies import (
            get_hashids_strategy_from_instance_or_cls,
        )

        strategy = get_hashids_strategy_from_instance_or_cls(model_cls)
        return strategy.queryset_annotator.get_annotations(model_cls)


class DjangoObjectTypeWithPkField(DjangoObjectType):
    class Meta:
        abstract = True

    pk = graphene.Int(required=True)

    def resolve_pk(root, info):
        return root.pk
