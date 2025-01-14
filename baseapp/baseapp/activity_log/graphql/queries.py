import graphene
from django.db.models import Q
from graphene_django.filter import DjangoFilterConnectionField

from ..models import ActivityLog
from .object_types import ActivityLogObjectType, VisibilityTypesEnum


class ActivityLogQueries:
    activity_logs = DjangoFilterConnectionField(
        ActivityLogObjectType,
        visibility=VisibilityTypesEnum(),
        first=graphene.Int(default_value=10),
        max_limit=100,
        user_name=graphene.String(),
    )

    def resolve_activity_logs(self, info, user_name=None, visibility=None, **kwargs):
        logs = ActivityLog.objects.all()
        if user_name:
            logs = logs.filter(
                Q(user__first_name__icontains=user_name) | Q(user__last_name__icontains=user_name)
            )
        return logs
