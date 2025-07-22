from grapple.schema import schema as grapple_schema

try:
    WagtailMutation = grapple_schema.Mutation
except AttributeError:

    class WagtailMutation:
        pass
