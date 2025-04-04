import channels_graphql_ws
import graphene
import swapper
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ObjectDoesNotExist

Comment = swapper.load_model("baseapp_comments", "Comment")
CommentObjectType = Comment.get_graphql_object_type()


class OnCommentChange(channels_graphql_ws.Subscription):
    created_comment = graphene.Field(CommentObjectType._meta.connection.Edge)
    updated_comment = graphene.Field(CommentObjectType)
    deleted_comment_id = graphene.ID()

    # Leave only latest 64 messages in the server queue.
    notification_queue_limit = 64

    class Arguments:
        target_object_id = graphene.ID()

    @staticmethod
    def subscribe(root, info, target_object_id=None):
        user = info.context.channels_scope.get("user", AnonymousUser())
        groups = []

        if not target_object_id:
            if user.has_perm("baseapp_comments.view_all_comment"):
                return ["all"]

        CAN_ANONYMOUS_VIEW_COMMENTS = getattr(
            settings, "BASEAPP_COMMENTS_CAN_ANONYMOUS_VIEW_COMMENTS", True
        )
        if not CAN_ANONYMOUS_VIEW_COMMENTS and not user.is_authenticated:
            return []

        if target_object_id:
            groups.append(target_object_id)

        return groups

    @staticmethod
    def publish(payload, info, target_object_id=None, in_reply_to_id=None):
        created_comment = payload.get("created_comment", None)
        updated_comment = payload.get("updated_comment", None)
        deleted_comment_id = payload.get("deleted_comment_id", None)

        user = info.context.channels_scope.get("user", AnonymousUser())
        # info.context.user = user

        CAN_ANONYMOUS_VIEW_COMMENTS = getattr(
            settings, "BASEAPP_COMMENTS_CAN_ANONYMOUS_VIEW_COMMENTS", True
        )
        if not CAN_ANONYMOUS_VIEW_COMMENTS and not user.is_authenticated:
            return None

        if created_comment:
            created_comment = CommentObjectType._meta.connection.Edge(node=created_comment)

        return OnCommentChange(
            created_comment=created_comment,
            updated_comment=updated_comment,
            deleted_comment_id=deleted_comment_id,
        )

    @classmethod
    def send_created_comment(cls, comment):
        # if hasattr(comment, "_sent_created_comment_subscription_event"):
        #     return
        # comment._sent_created_comment_subscription_event = True

        groups = ["all"]

        # only send to the target and in_reply_to if it exists
        # with this we don't send replies if the user don't have replies open
        if comment.in_reply_to_id:
            groups.append(comment.in_reply_to.relay_id)
        elif comment.target_object_id:
            try:
                target = comment.target_content_type.get_object_for_this_type(
                    pk=comment.target_object_id
                )
                groups.append(target.relay_id)
            except ObjectDoesNotExist:
                pass

        for group_name in groups:
            cls.broadcast(
                group=group_name,
                payload={"created_comment": comment},
            )

    @classmethod
    def send_updated_comment(cls, comment):
        # if hasattr(comment, "_sent_updated_comment_subscription_event"):
        #     return
        # comment._sent_updated_comment_subscription_event = True

        groups = ["all"]
        if comment.target_object_id and comment.target and comment.target.relay_id:
            groups.append(comment.target.relay_id)

        if comment.in_reply_to_id:
            groups.append(comment.in_reply_to.relay_id)

        for group_name in groups:
            cls.broadcast(
                group=group_name,
                payload={"updated_comment": comment},
            )

    @classmethod
    def send_delete_comment(cls, comment_replay_id, target_relay_id, in_reply_to_relay_id):
        # if hasattr(comment, "_sent_deleted_comment_subscription_event"):
        #     return
        # comment._sent_deleted_comment_subscription_event = True

        groups = ["all"]
        if target_relay_id:
            groups.append(target_relay_id)

        if in_reply_to_relay_id:
            groups.append(in_reply_to_relay_id)

        for group_name in groups:
            cls.broadcast(
                group=group_name,
                payload={"deleted_comment_id": comment_replay_id},
            )


class CommentsSubscriptions:
    on_comment_change = OnCommentChange.Field()
