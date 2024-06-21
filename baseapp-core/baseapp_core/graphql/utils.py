import graphene
from graphene_django.registry import get_global_registry
from graphql_relay import to_global_id
from graphql_relay.node.node import from_global_id


def get_pk_from_relay_id(relay_id):
    gid_type, gid = from_global_id(relay_id)
    return gid


def get_obj_from_relay_id(info: graphene.ResolveInfo, relay_id):
    gid_type, gid = from_global_id(relay_id)
    object_type = info.schema.get_type(gid_type)
    return object_type.graphene_type.get_node(info, gid)


def get_obj_relay_id(obj):
    object_type = _cache_object_type(obj)
    return to_global_id(object_type._meta.name, obj.pk)


def _cache_object_type(obj):
    if not hasattr(obj, "_graphql_object_type"):
        registry = get_global_registry()
        obj._graphql_object_type = registry.get_type_for_model(obj._meta.concrete_model)
    return obj._graphql_object_type


def get_object_type_for_model(model):
    def get_object_type():
        return model.get_graphql_object_type()

    return get_object_type
