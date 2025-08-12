import graphene

from baseapp_wagtail.base.graphql.interfaces import URLPathTargetWagtailInterface


class WagtailPageObjectType(graphene.ObjectType):
    class Meta:
        interfaces = (URLPathTargetWagtailInterface,)
        name = "WagtailPage"
