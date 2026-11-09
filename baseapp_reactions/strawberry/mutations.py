import strawberry
import swapper
from django.apps import apps
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError
from strawberry import UNSET
from strawberry.types import Info

from baseapp_core.graphql import get_obj_from_relay_id
from baseapp_core.models import DocumentId
from baseapp_core.plugins import shared_services
from baseapp_core.strawberry import (
    RelayMutationInput,
    RelayMutationPayload,
    relay_mutation,
)
from baseapp_core.strawberry.connections import Edge, offset_to_cursor

from .interfaces import ReactionsInterface
from .types import ReactionLazyType, ReactionTypesEnum

Reaction = swapper.load_model("baseapp_reactions", "Reaction")


def _permission_error() -> GraphQLError:
    return GraphQLError(
        str(_("You don't have permission to perform this action")),
        extensions={"code": "permission_required"},
    )


@strawberry.input(name="ReactionToggleInput")
class ReactionToggleInput(RelayMutationInput):
    target_object_id: strawberry.ID
    reaction_type: ReactionTypesEnum
    if apps.is_installed("baseapp_profiles"):
        profile_object_id: strawberry.ID | None = UNSET


@strawberry.type(name="ReactionTogglePayload")
class ReactionTogglePayload(RelayMutationPayload):
    reaction: Edge[ReactionLazyType] | None = None
    target: ReactionsInterface | None = None
    reaction_deleted_id: strawberry.ID | None = None


@strawberry.type
class ReactionsMutations:
    @relay_mutation(login_required=True)
    def reaction_toggle(
        self, info: Info, input: ReactionToggleInput
    ) -> ReactionTogglePayload | None:
        user = info.context.user
        target = get_obj_from_relay_id(info, input.target_object_id)
        target_document = DocumentId.get_or_create_for_object(target)
        reaction_type = input.reaction_type
        activity_name = "baseapp_reactions.add_reaction"

        if not user.has_perm(activity_name, target):
            raise _permission_error()

        if service := shared_services.get("activity_log"):
            service.set_public_activity(verb=activity_name)

        if apps.is_installed("baseapp_profiles"):
            profile = user.current_profile
            if input.profile_object_id:
                profile = get_obj_from_relay_id(info, input.profile_object_id)

            if not user.has_perm("baseapp_reactions.add_reaction_with_profile", profile):
                raise _permission_error()

            reaction, created = Reaction.objects.get_or_create(
                profile=profile,
                target_document=target_document,
                defaults={"reaction_type": reaction_type, "user": user},
            )
        else:
            reaction, created = Reaction.objects.get_or_create(
                user=user,
                target_document=target_document,
                defaults={"reaction_type": reaction_type},
            )
        if not created:
            if reaction.reaction_type == reaction_type:
                if not user.has_perm("baseapp_reactions.delete_reaction", reaction):
                    raise _permission_error()

                reaction_deleted_id = reaction.relay_id
                reaction.delete()
                target.refresh_from_db()
                return ReactionTogglePayload(target=target, reaction_deleted_id=reaction_deleted_id)

            if not user.has_perm("baseapp_reactions.change_reaction", reaction):
                raise _permission_error()

            reaction.reaction_type = reaction_type
            reaction.save()

        target.refresh_from_db()

        return ReactionTogglePayload(
            reaction=Edge(node=reaction, cursor=offset_to_cursor(0)), target=target
        )
