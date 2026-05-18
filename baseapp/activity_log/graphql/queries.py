from typing import Any, Optional

import graphene
from django.db.models import QuerySet
from graphene_django.filter import DjangoFilterConnectionField

from ..models import ActivityLog
from .object_types import ActivityLogObjectType, VisibilityTypesEnum


class ActivityLogQueries:
    activity_logs = DjangoFilterConnectionField(
        ActivityLogObjectType,
        visibility=VisibilityTypesEnum(),
        first=graphene.Int(default_value=10),
        max_limit=100,
    )

    def resolve_activity_logs(
        self, info: graphene.ResolveInfo, visibility: Optional[str] = None, **kwargs: Any
    ) -> QuerySet:  # NOSONAR
        return ActivityLog.objects.all()
