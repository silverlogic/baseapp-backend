import graphene
import swapper
from baseapp_core.graphql import RelayMutation, login_required
from baseapp_core.utils import get_content_type_by_natural_key
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError
from graphql_relay.connection.arrayconnection import offset_to_cursor
from graphql_relay.node.node import from_global_id

from .object_types import FollowNode, FollowsInterface

Follow = swapper.load_model("baseapp_follows", "Follow")


class FollowToggle(RelayMutation):
    follow = graphene.Field(FollowNode._meta.connection.Edge, required=False)
    target = graphene.Field(FollowsInterface)
    actor = graphene.Field(FollowsInterface)
    follow_deleted_id = graphene.ID(required=False)

    class Input:
        actor_object_id = graphene.ID(required=True)
        actor_content_type = graphene.String(
            required=False,
            description=_(
                "This overrides the GraphQL Type found in Relay's Global ID. Please use app.Model format."
            ),
        )
        target_object_id = graphene.ID(required=True)
        target_content_type = graphene.String(
            required=False,
            description=_(
                "This overrides the GraphQL Type found in Relay's Global ID. Please use app.Model format."
            ),
        )

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        gid_type, gid = from_global_id(input.get("target_object_id"))
        object_type = info.schema.get_type(gid_type)
        target = object_type.graphene_type.get_node(info, gid)

        target_content_type = input.get("target_content_type")
        if target_content_type:
            target_content_type = get_content_type_by_natural_key(target_content_type)
            target = target_content_type.get_object_for_this_type(pk=gid)
        else:
            target_content_type = ContentType.objects.get_for_model(target)

        gid_type, gid = from_global_id(input.get("actor_object_id"))
        object_type = info.schema.get_type(gid_type)
        actor = object_type.graphene_type.get_node(info, gid)

        actor_content_type = input.get("actor_content_type")
        if actor_content_type:
            actor_content_type = get_content_type_by_natural_key(actor_content_type)
            actor = actor_content_type.get_object_for_this_type(pk=gid)
        else:
            actor_content_type = ContentType.objects.get_for_model(actor)

        if not info.context.user.has_permission("follow.as_actor", actor):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        if not info.context.user.has_permission("follow.add_follow", target):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        follow, created = Follow.objects.get_or_create(
            actor_object_id=actor.pk,
            actor_content_type=actor_content_type,
            target_object_id=target.pk,
            target_content_type=target_content_type,
        )

        if not created:
            if not info.context.user.has_permission("follow.delete_follow", follow):
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
            follow=FollowNode._meta.connection.Edge(node=follow, cursor=offset_to_cursor(0)),
            target=target,
            actor=actor,
        )


class FollowsMutations(object):
    follow_toggle = FollowToggle.Field()
