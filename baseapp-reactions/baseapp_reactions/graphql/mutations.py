import graphene
import swapper
from baseapp_core.graphql import RelayMutation, get_obj_from_relay_id, login_required
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError
from graphql_relay.connection.arrayconnection import offset_to_cursor

from .object_types import ReactionObjectType, ReactionsInterface, ReactionTypesEnum

Reaction = swapper.load_model("baseapp_reactions", "Reaction")


class ReactionToggle(RelayMutation):
    reaction = graphene.Field(ReactionObjectType._meta.connection.Edge, required=False)
    target = graphene.Field(ReactionsInterface)
    reaction_deleted_id = graphene.ID(required=False)

    class Input:
        target_object_id = graphene.ID(required=True)
        profile_object_id = graphene.ID(required=False)
        reaction_type = graphene.Field(ReactionTypesEnum, required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        target = get_obj_from_relay_id(info, input.get("target_object_id"))
        target_content_type = ContentType.objects.get_for_model(target)
        reaction_type = input["reaction_type"]
        profile = None

        if not info.context.user.has_perm("baseapp_reactions.add_reaction", target):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        if input.get("profile_object_id"):
            profile = get_obj_from_relay_id(info, input.get("profile_object_id"))
            if not info.context.user.has_perm(
                "baseapp_reactions.add_reaction_with_profile", profile
            ):
                raise GraphQLError(
                    str(_("You don't have permission to perform this action")),
                    extensions={"code": "permission_required"},
                )

        reaction, created = Reaction.objects.get_or_create(
            profile=profile,
            target_object_id=target.pk,
            target_content_type=target_content_type,
            defaults={"reaction_type": reaction_type, "user": info.context.user},
        )
        if not created:
            if reaction.reaction_type == reaction_type:
                if not info.context.user.has_perm("baseapp_reactions.delete_reaction", reaction):
                    raise GraphQLError(
                        str(_("You don't have permission to perform this action")),
                        extensions={"code": "permission_required"},
                    )

                reaction_deleted_id = reaction.relay_id
                reaction.delete()
                target.refresh_from_db()
                return ReactionToggle(target=target, reaction_deleted_id=reaction_deleted_id)

            if not info.context.user.has_perm("baseapp_reactions.change_reaction", reaction):
                raise GraphQLError(
                    str(_("You don't have permission to perform this action")),
                    extensions={"code": "permission_required"},
                )

            reaction.reaction_type = reaction_type
            reaction.save()

        target.refresh_from_db()

        return ReactionToggle(
            reaction=ReactionObjectType._meta.connection.Edge(
                node=reaction, cursor=offset_to_cursor(0)
            ),
            target=target,
        )


class ReactionsMutations(object):
    reaction_toggle = ReactionToggle.Field()
