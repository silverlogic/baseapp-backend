from graphene.relay import Node as GrapheneRelayNode


class Node(GrapheneRelayNode):
    @classmethod
    def get_node_from_global_id(cls, info, global_id, only_type=None):
        graphene_type = None
        _type = None

        try:
            _id = int(global_id)
        except ValueError:
            _type, _id = cls.resolve_global_id(info, global_id)

        if _type:
            graphene_type = info.schema.get_type(_type)
            if graphene_type is None:
                raise Exception(f'Relay Node "{_type}" not found in schema')
            graphene_type = graphene_type.graphene_type
        elif only_type:
            graphene_type = only_type
        else:
            raise Exception("Couldn't resolve the type of the node.")

        if only_type:
            assert graphene_type == only_type, f"Must receive a {only_type._meta.name} id."

        # We make sure the ObjectType implements the "Node" interface
        if GrapheneRelayNode not in graphene_type._meta.interfaces:
            raise Exception(
                f'ObjectType "{graphene_type._meta.name}" does not implement the "{GrapheneRelayNode}" interface.'
            )

        get_node = getattr(graphene_type, "get_node", None)
        if get_node:
            return get_node(info, _id)
