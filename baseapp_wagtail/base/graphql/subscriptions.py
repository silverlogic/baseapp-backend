from grapple.schema import schema as grapple_schema


try:
    WagtailSubscription = grapple_schema.Subscription
except AttributeError:
    class WagtailSubscription:
        pass
