from __future__ import unicode_literals
import graphene

from baseapp_wagtail.base.graphql.object_types_old import WagtailPageObjectType
from testproject.base.models import StandardPage


class WagtailPagesQueries:
    pages = graphene.List(WagtailPageObjectType)

    def resolve_pages(self, info):
        return StandardPage.objects.live()
