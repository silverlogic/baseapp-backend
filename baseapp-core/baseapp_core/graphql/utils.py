from graphene_django.registry import get_global_registry
from graphql_relay import to_global_id
from graphql_relay.node.node import from_global_id


def get_pk_from_relay_id(relay_id):
    gid_type, gid = from_global_id(relay_id)
    return gid


def get_obj_from_relay_id(info, relay_id):
    gid_type, gid = from_global_id(relay_id)
    object_type = info.schema.get_type(gid_type)
    return object_type.graphene_type.get_node(info, gid)


def get_obj_relay_id(obj):
    registry = get_global_registry()
    object_type = registry.get_type_for_model(obj._meta.concrete_model)
    return to_global_id(object_type._meta.name, obj.pk)
