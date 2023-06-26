from graphql_relay.node.node import from_global_id


def get_pk_from_relay_id(relay_id):
    gid_type, gid = from_global_id(relay_id)
    return gid


def get_obj_from_relay_id(info, relay_id):
    gid_type, gid = from_global_id(relay_id)
    object_type = info.schema.get_type(gid_type)
    return object_type.graphene_type.get_node(info, gid)
