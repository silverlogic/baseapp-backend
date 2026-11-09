import strawberry
import swapper
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError
from strawberry.types import Info

from baseapp_core.models import DocumentId
from baseapp_core.strawberry import (
    RelayMutationInput,
    RelayMutationPayload,
    relay_mutation,
)
from baseapp_core.strawberry.connections import Edge, offset_to_cursor
from baseapp_core.strawberry.relay import get_instance_from_global_id

from .interfaces import FollowsInterface
from .types import FollowLazyType

Follow = swapper.load_model("baseapp_follows", "Follow")


def _permission_error() -> GraphQLError:
    return GraphQLError(
        str(_("You don't have permission to perform this action")),
        extensions={"code": "permission_required"},
    )


@strawberry.input(name="FollowToggleInput")
class FollowToggleInput(RelayMutationInput):
    actor_object_id: strawberry.ID
    target_object_id: strawberry.ID


@strawberry.type(name="FollowTogglePayload")
class FollowTogglePayload(RelayMutationPayload):
    follow: Edge[FollowLazyType] | None = None
    target: FollowsInterface | None = None
    actor: FollowsInterface | None = None
    follow_deleted_id: strawberry.ID | None = None


@strawberry.type
class FollowsMutations:
    @relay_mutation(login_required=True)
    def follow_toggle(self, info: Info, input: FollowToggleInput) -> FollowTogglePayload | None:
        user = info.context.user
        target_obj = get_instance_from_global_id(info, input.target_object_id)
        actor_obj = get_instance_from_global_id(info, input.actor_object_id)

        if not user.has_perm("baseapp_follows.add_follow_with_profile", actor_obj):
            raise _permission_error()
        if not user.has_perm("baseapp_follows.add_follow", target_obj):
            raise _permission_error()

        actor_doc = DocumentId.get_or_create_for_object(actor_obj)
        target_doc = DocumentId.get_or_create_for_object(target_obj)

        follow, created = Follow.objects.get_or_create(
            actor=actor_doc, target=target_doc, defaults={"user": user}
        )

        if not created:
            if not user.has_perm("baseapp_follows.delete_follow", follow):
                raise _permission_error()

            # Owners can't unfollow their own entities, except profile-to-profile follows
            content_obj = follow.target.content_object
            if (
                hasattr(content_obj, "owner_id")
                and content_obj.owner_id == user.id
                and not follow._is_profile_to_profile()
            ):
                raise GraphQLError(
                    str(_("The owner cannot leave")), extensions={"code": "owner_cannot_leave"}
                )

            follow_deleted_id = follow.relay_id
            follow.delete()
            return FollowTogglePayload(
                target=target_obj, actor=actor_obj, follow_deleted_id=follow_deleted_id
            )

        return FollowTogglePayload(
            follow=Edge(node=follow, cursor=offset_to_cursor(0)), target=target_obj, actor=actor_obj
        )
