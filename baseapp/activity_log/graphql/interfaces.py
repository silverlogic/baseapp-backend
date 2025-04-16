import graphene
from graphene_django.filter import DjangoFilterConnectionField

from ..models import ActivityLog
from .object_types import ActivityLogObjectType, VisibilityTypesEnum


class NodeActivityLogInterface(graphene.Interface):
    node_activity_logs = DjangoFilterConnectionField(
        ActivityLogObjectType,
        visibility=VisibilityTypesEnum(),
        first=graphene.Int(default_value=10),
        max_limit=100,
    )

    def resolve_node_activity_logs(self, info, **kwargs):
        if not info.context.user.has_perm("activity_log.list_node_activitylog", self):
            return ActivityLog.objects.none()
        context_ids = self.pgh_event_model.objects.filter(pgh_obj_id=self.pk).values_list(
            "pgh_context_id", flat=True
        )
        return ActivityLog.objects.filter(pk__in=context_ids)


class UserActivityLog:
    activity_logs = DjangoFilterConnectionField(
        ActivityLogObjectType,
        visibility=VisibilityTypesEnum(),
        first=graphene.Int(default_value=10),
        max_limit=100,
    )

    def resolve_activity_logs(self, info, **kwargs):
        if not info.context.user.has_perm("activity_log.list_user_activitylog", self):
            return ActivityLog.objects.none()
        return ActivityLog.objects.filter(user_id=self.pk)


class ProfileActivityLog:
    activity_logs = DjangoFilterConnectionField(
        ActivityLogObjectType,
        visibility=VisibilityTypesEnum(),
        first=graphene.Int(default_value=10),
        max_limit=100,
    )

    def resolve_activity_logs(self, info, **kwargs):
        if not info.context.user.has_perm("activity_log.list_profile_activitylog", self):
            return ActivityLog.objects.none()
        return ActivityLog.objects.filter(profile_id=self.pk)
