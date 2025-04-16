import graphene
import swapper
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError
from graphql_relay import offset_to_cursor

from baseapp_core.graphql import RelayMutation, get_obj_from_relay_id, login_required

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
        target = get_obj_from_relay_id(info, input.get("target_object_id"))
        actor = get_obj_from_relay_id(info, input.get("actor_object_id"))

        if not info.context.user.has_perm("baseapp_follows.add_follow_with_profile", actor):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        if not info.context.user.has_perm("baseapp_follows.add_follow", target):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        follow, created = Follow.objects.get_or_create(
            actor=actor,
            target=target,
        )

        if not created:
            if not info.context.user.has_perm("baseapp_follows.delete_follow", follow):
                raise GraphQLError(
                    str(_("You don't have permission to perform this action")),
                    extensions={"code": "permission_required"},
                )

            follow_deleted_id = follow.relay_id
            follow.delete()
            target.refresh_from_db()
            actor.refresh_from_db()
            return FollowToggle(target=target, actor=actor, follow_deleted_id=follow_deleted_id)

        target.refresh_from_db()
        actor.refresh_from_db()

        return FollowToggle(
            follow=FollowObjectType._meta.connection.Edge(node=follow, cursor=offset_to_cursor(0)),
            target=target,
            actor=actor,
        )


class FollowsMutations(object):
    follow_toggle = FollowToggle.Field()
