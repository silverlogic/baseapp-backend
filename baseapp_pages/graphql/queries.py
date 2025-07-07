import graphene
import swapper
from django.db.models import Q
from django.utils.translation import get_language
from baseapp_core.graphql import Node
from graphene_django.filter import DjangoFilterConnectionField

from ..models import URLPath
from .object_types import URLPathNode

# TODO: Fix in next story
# https://app.approvd.io/silverlogic/BA/stories/36399
# Resolve GraphQL Conflicts and Sync Metadata with baseapp-pages
# from baseapp_core.graphql import Node


Page = swapper.load_model("baseapp_pages", "Page")
PageObjectType = Page.get_graphql_object_type()


class PagesQueries:
    url_path = graphene.Field(URLPathNode, path=graphene.String(required=True))
    all_pages = DjangoFilterConnectionField(PageObjectType)
    ba_page = Node.Field(PageObjectType)

    def resolve_url_path(self, info, path):
        language = get_language()

        try:
            url_path = URLPath.objects.get(
                Q(language=language) | Q(language__isnull=True), path=path
            )
        except URLPath.DoesNotExist:
            return None

        if not url_path.is_active:
            active_url_path = URLPath.objects.filter(
                target_content_type_id=url_path.target_content_type_id,
                target_object_id=url_path.target_object_id,
                language=language,
                is_active=True,
            ).first()
            if active_url_path:
                url_path = active_url_path

        return url_path
