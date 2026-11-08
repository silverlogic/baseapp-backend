from typing import Any, Optional

import strawberry
from django.db.models import Q
from django.utils.translation import get_language
from strawberry.types import Info

from baseapp_core.strawberry import CountedConnection
from baseapp_core.strawberry.connections import connection
from baseapp_core.strawberry.relay import typed_node_field

from ..graphql.object_types import PageFilter
from ..models import URLPath
from .interfaces import URLPathLazyType
from .types import PageLazyType


@strawberry.type
class PagesQueries:
    all_pages = connection(CountedConnection[PageLazyType] | None, filterset_class=PageFilter)
    page = typed_node_field(PageLazyType)

    @strawberry.field(graphql_type=Optional[URLPathLazyType])
    def url_path(self, info: Info, path: str) -> Any:
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
