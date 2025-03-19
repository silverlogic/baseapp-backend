import graphene

# from graphene_django import DjangoObjectType as GrapheneDjangoObjectType
from query_optimizer import DjangoObjectType as OptimizerDjangoObjectType

from .connections import CountedConnection


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
