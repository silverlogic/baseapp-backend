import graphene
import swapper
from baseapp_core.graphql import RelayMutation, login_required
from baseapp_core.utils import get_content_type_by_natural_key
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError
from graphql_relay import to_global_id
from graphql_relay.connection.arrayconnection import offset_to_cursor
from graphql_relay.node.node import from_global_id

from .object_types import ReactionNode, ReactionsNode, ReactionTypesEnum

Reaction = swapper.load_model("baseapp_reactions", "Reaction")


class ReactionToggle(RelayMutation):
    reaction = graphene.Field(ReactionNode._meta.connection.Edge, required=False)
    target = graphene.Field(ReactionsNode)
    reaction_deleted_id = graphene.ID(required=False)

    class Input:
        target_object_id = graphene.ID(required=True)
        target_content_type = graphene.String(
            required=False,
            description=_(
                "This overrides the GraphQL Type found in Relay's Global ID. Please use app.Model format."
            ),
        )
        reaction_type = graphene.Field(ReactionTypesEnum, required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        gid_type, gid = from_global_id(input.get("target_object_id"))
        object_type = info.schema.get_type(gid_type)
        target = object_type.graphene_type.get_node(info, gid)
        reaction_type = input["reaction_type"]

        target_content_type = input.get("target_content_type")
        if target_content_type:
            content_type = get_content_type_by_natural_key(target_content_type)
            target = content_type.get_object_for_this_type(pk=gid)
        else:
            content_type = ContentType.objects.get_for_model(target)

        # check https://github.com/queplanta/backend/blob/master/accounts/permissions.py#L9
        if "reaction-add" not in target.get_my_permissions(info.context):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )
            # return cls(e)
        # target.has_permission(info.context, 'reaction')

        reaction, created = Reaction.objects.get_or_create(
            user=info.context.user,
            target_object_id=target.pk,
            target_content_type=content_type,
            defaults={"reaction_type": reaction_type},
        )
        if not created:
            if reaction.reaction_type == reaction_type:
                if "reaction-delete" not in target.get_my_permissions(info.context):
                    raise GraphQLError(
                        str(_("You don't have permission to perform this action")),
                        extensions={"code": "permission_required"},
                    )

                reaction_deleted_id = to_global_id(ReactionNode._meta.name, reaction.pk)
                reaction.delete()
                target.refresh_from_db()
                return ReactionToggle(target=target, reaction_deleted_id=reaction_deleted_id)

            if "reaction-change" not in target.get_my_permissions(info.context):
                raise GraphQLError(
                    str(_("You don't have permission to perform this action")),
                    extensions={"code": "permission_required"},
                )

            reaction.reaction_type = reaction_type
            reaction.save()

        target.refresh_from_db()

        return ReactionToggle(
            reaction=ReactionNode._meta.connection.Edge(node=reaction, cursor=offset_to_cursor(0)),
            target=target,
        )


class ReactionsMutations(object):
    reaction_toggle = ReactionToggle.Field()
