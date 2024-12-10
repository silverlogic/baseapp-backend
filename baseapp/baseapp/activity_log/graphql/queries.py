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
        ActivityLogGroupType,
        visibility=VisibilityTypesEnum(),
        interval_minutes=graphene.Int(default_value=15),
    )

    def resolve_activity_logs(self, info, visibility=None, **kwargs):
        return ActivityLog.objects.all()

    def resolve_activity_log_groups(self, info, interval_minutes, visibility=None, **kwargs):
        logs = ActivityLog.objects.all()
        grouped_logs = {}
        for log in logs:
            user_id = log.user_id
            timestamp = log.created_at
            if user_id not in grouped_logs:
                grouped_logs[user_id] = []
            if not grouped_logs[user_id] or (timestamp - grouped_logs[user_id][-1][-1].created_at).total_seconds() > interval_minutes * 60:
                grouped_logs[user_id].append([log])
            else:
                grouped_logs[user_id][-1].append(log)

        result = []
        for user_id, groups in grouped_logs.items():
            for group in groups:
                result.append(ActivityLogGroupType(
                    user_id=user_id,
                    logs=group,
                    last_activity_timestamp=group[-1].created_at
                ))
        result.sort(key=lambda x: x.last_activity_timestamp, reverse=True)
        return result
