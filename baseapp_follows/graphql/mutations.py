import graphene
import swapper
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError
from graphql_relay import offset_to_cursor

from baseapp_core.graphql import RelayMutation, get_obj_from_relay_id, login_required
from baseapp_core.models import DocumentId

from .interfaces import FollowsInterface

Follow = swapper.load_model("baseapp_follows", "Follow")
FollowObjectType = Follow.get_graphql_object_type()


class FollowToggle(RelayMutation):
    follow = graphene.Field(
        lambda: Follow.get_graphql_object_type()._meta.connection.Edge, required=False
    )
    target = graphene.Field(FollowsInterface)
    actor = graphene.Field(FollowsInterface)
    follow_deleted_id = graphene.ID(required=False)

    class Input:
        actor_object_id = graphene.ID(required=True)
        target_object_id = graphene.ID(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        target_obj = get_obj_from_relay_id(info, input.get("target_object_id"))
        actor_obj = get_obj_from_relay_id(info, input.get("actor_object_id"))

        if not info.context.user.has_perm("baseapp_follows.add_follow_with_profile", actor_obj):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        if not info.context.user.has_perm("baseapp_follows.add_follow", target_obj):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        # Convert to DocumentIds
        actor_doc = DocumentId.get_or_create_for_object(actor_obj)
        target_doc = DocumentId.get_or_create_for_object(target_obj)

        follow, created = Follow.objects.get_or_create(
            actor=actor_doc,
            target=target_doc,
            defaults={"user": info.context.user},
        )

        if not created:
            if not info.context.user.has_perm("baseapp_follows.delete_follow", follow):
                raise GraphQLError(
                    str(_("You don't have permission to perform this action")),
                    extensions={"code": "permission_required"},
                )

            # Prevent owners from unfollowing their own entities,
            # but allow profile-to-profile unfollows (cross-profile actions by the same user)
            content_obj = follow.target.content_object
            if (
                hasattr(content_obj, "owner_id")
                and content_obj.owner_id == info.context.user.id
                and not follow._is_profile_to_profile()
            ):
                raise GraphQLError(
                    str(_("The owner cannot leave")),
                    extensions={"code": "owner_cannot_leave"},
                )

            follow_deleted_id = follow.relay_id
            follow.delete()
            return FollowToggle(
                target=target_obj, actor=actor_obj, follow_deleted_id=follow_deleted_id
            )

        return FollowToggle(
            follow=FollowObjectType._meta.connection.Edge(node=follow, cursor=offset_to_cursor(0)),
            target=target_obj,
            actor=actor_obj,
        )


class FollowsMutations(object):
    follow_toggle = FollowToggle.Field()
