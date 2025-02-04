import channels_graphql_ws
import graphene
from channels.db import database_sync_to_async

from baseapp_core.graphql import get_obj_from_relay_id

from .object_types import ActivityLogObjectType


class OnNewActivityLogMessage(channels_graphql_ws.Subscription):
    message = graphene.Field(lambda: ActivityLogObjectType._meta.connection.Edge)

    class Arguments:
        room_id = graphene.ID(required=True)

    @staticmethod
    def subscribe(root, info, room_id):
        room = database_sync_to_async(get_obj_from_relay_id)(info, room_id)

        user = info.context.channels_scope["user"]
        if not user.is_authenticated or not database_sync_to_async(user.has_perm)(
            "activity_log.view_activitylog", room
        ):
            return []
        return [room_id]

    @staticmethod
    def publish(payload, info, room_id):
        message = payload["message"]
        user = info.context.channels_scope["user"]

        if not user.is_authenticated:
            return None

        return OnNewActivityLogMessage(
            message=ActivityLogObjectType._meta.connection.Edge(node=message)
        )

    @classmethod
    def new_message(cls, message, room_id):
        cls.broadcast(
            group=room_id,
            payload={"message": message},
        )
        OnNewActivityLogMessage.new_message(message=message)


class ActivityLogSubscriptions:
    on_new_activity_log = OnNewActivityLogMessage.Field()
