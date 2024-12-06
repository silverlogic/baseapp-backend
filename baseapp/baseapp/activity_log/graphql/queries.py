import graphene
from graphene_django.filter import DjangoFilterConnectionField

from ..models import ActivityLog
from .object_types import (
    ActivityLogGroupType,
    ActivityLogObjectType,
    VisibilityTypesEnum,
)


class ActivityLogQueries:
    activity_logs = DjangoFilterConnectionField(
        ActivityLogObjectType,
        visibility=VisibilityTypesEnum(),
        first=graphene.Int(default_value=10),
        max_limit=100,
    )

    activity_log_groups = graphene.List(
        ActivityLogGroupType, interval_minutes=graphene.Int(default_value=15)
    )

    def resolve_activity_log(self, info, visibility=None, **kwargs):
        return ActivityLog.objects.all()

    def resolve_activity_log_groups(self, info, interval_minutes, **kwargs):
        grouped_logs = ActivityLog.objects.grouped_by_interval(interval_minutes)
        groups = {}
        for log in grouped_logs:
            interval_start = log.interval_start
            if interval_start not in groups:
                groups[interval_start] = []
            groups[interval_start].append(log)
        return [
            ActivityLogGroupType(interval_start=key, logs=value) for key, value in groups.items()
        ]
