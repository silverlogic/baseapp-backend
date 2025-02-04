import graphene
import swapper
from django.apps import apps
from django.contrib.auth import get_user_model
from graphene import relay
from graphene.types.generic import GenericScalar
from graphene_django.filter import DjangoFilterConnectionField
from pghistory.models import MiddlewareEvents

from baseapp_core.graphql import DjangoObjectType, get_object_type_for_model

from ..models import ActivityLog, VisibilityTypes
from .filters import ActivityLogFilter, MiddlewareEventFilter

User = get_user_model()
Profile = swapper.load_model("baseapp_profiles", "Profile")
VisibilityTypesEnum = graphene.Enum.from_enum(VisibilityTypes)


class NodeLogEventObjectType(DjangoObjectType):
    obj = graphene.Field(relay.Node, description="The object of the event.")
    label = graphene.String(description="The event label.")
    data = GenericScalar(description="The raw data of the event.")
    diff = GenericScalar(description="The diff between the previous event of the same label.")
    created_at = graphene.DateTime(description="When the event was created.")

    class Meta:
        interfaces = (relay.Node,)
        model = MiddlewareEvents
        name = "NodeLogEvent"
        fields = (
            "id",
            "obj",
            "data",
            "created_at",
            "diff",
            "user",
            "label",
        )
        filterset_class = MiddlewareEventFilter

    def resolve_data(self, info, **kwargs):
        if info.context.user.has_perm("activity_log.view_nodelogevent-data", self):
            return self.pgh_data

    def resolve_obj(self, info, **kwargs):
        Model = apps.get_model(self.pgh_obj_model)
        try:
            return Model.objects.get(pk=self.pgh_obj_id)
        except Model.DoesNotExist:
            return None

    def resolve_created_at(self, info, **kwargs):
        return self.pgh_created_at

    def resolve_diff(self, info, **kwargs):
        if info.context.user.has_perm("activity_log.view_nodelogevent-diff", self):
            return self.pgh_diff

    def resolve_label(self, info, **kwargs):
        return self.pgh_label


class BaseActivityLogObjectType:
    metadata = GenericScalar()
    events = DjangoFilterConnectionField(lambda: NodeLogEventObjectType)
    user = graphene.Field(get_object_type_for_model(User))
    profile = graphene.Field(get_object_type_for_model(Profile))
    visibility = graphene.Field(VisibilityTypesEnum)
    verb = graphene.String()
    ip_address = graphene.String()
    url = graphene.String()

    @classmethod
    def get_node(cls, info, id):
        try:
            obj = cls._meta.model.objects.get(id=id)
            if not info.context.user.has_perm("activity_log.view_activitylog", obj):
                return None
            return obj

        except cls._meta.model.DoesNotExist:
            return None

    @classmethod
    def get_queryset(cls, queryset, info):
        if not info.context.user.has_perm("activity_log.list_activitylog_any_visibility"):
            queryset = queryset.filter(visibility=VisibilityTypes.PUBLIC)
        return queryset

    class Meta:
        interfaces = (relay.Node,)
        model = ActivityLog
        fields = (
            "id",
            "pk",
            "user",
            "url",
            "verb",
            "events",
            "visibility",
            "ip_address",
            "created_at",
            "updated_at",
        )
        filterset_class = ActivityLogFilter

    def resolve_events(self, info, **kwargs):
        return MiddlewareEvents.objects.filter(pgh_context_id=self.pk)


class ActivityLogObjectType(BaseActivityLogObjectType, DjangoObjectType):
    class Meta(BaseActivityLogObjectType.Meta):
        pass
