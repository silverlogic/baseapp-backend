from grapple.models import GraphQLField


def GraphQLDynamicField(field_name: str, field_type: type, **kwargs):
    """
    Args:
        field_name: str
        field_type: type - Must be a graphene scalar type.
        **kwargs: dict - Additional arguments for the GraphQLField.
    """

    def Mixin():
        return GraphQLField(field_name, field_type, **kwargs)

    return Mixin
