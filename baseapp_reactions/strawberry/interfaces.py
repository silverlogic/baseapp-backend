from collections.abc import Iterable
from typing import Any, Optional

import strawberry
import strawberry_django
import swapper
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model
from strawberry.types import Info

from baseapp_core.graphql import get_pk_from_relay_id
from baseapp_core.plugins import shared_services
from baseapp_core.strawberry import CountedConnection, Node, model_from_info
from baseapp_core.strawberry.connections import connection

from ..models import default_reactions_count
from ..permissions import can_anonymous_view_reactions
from .types import ReactionFilter, ReactionLazyType, ReactionsCount

Reaction = swapper.load_model("baseapp_reactions", "Reaction")


def _metadata_annotation(name: str) -> dict[str, Any]:
    """Optimizer hint: annotate one reactable metadata column on the implementing model."""

    def annotation(info: Info) -> Any:
        service = shared_services.get("reactable_metadata")
        return service.get_annotations(model_from_info(info))[name]

    return {name: annotation}


def _reactions_for(root: Model) -> Any:
    return Reaction.objects.filter(
        target_document__content_type=ContentType.objects.get_for_model(root),
        target_document__object_id=root.pk,
    )


def _resolve_my_reaction(root: Model, info: Info, profile_id: str | None = None) -> Any:
    user = info.context.user
    if not user.is_authenticated:
        return None
    if not apps.is_installed("baseapp_profiles"):
        return _reactions_for(root).filter(user_id=user.id).first()

    Profile = swapper.load_model("baseapp_profiles", "Profile")
    if profile_id:
        profile = Profile.objects.get_if_member(pk=get_pk_from_relay_id(profile_id), user=user)
    else:
        profile = user.current_profile
    if not profile:
        return None
    return _reactions_for(root).filter(profile_id=profile.pk).first()


@strawberry.interface(name="ReactionsInterface")
class ReactionsInterface(Node):
    """Reactions fields for any DocumentId-aware model. Optimizer hints live on the fields."""

    @strawberry_django.field(annotate=_metadata_annotation("_reactable_reactions_count"))
    def reactions_count(self, info: Info) -> ReactionsCount | None:
        if service := shared_services.get("reactable_metadata"):
            counts = service.get_reactions_count(self)
        else:
            counts = default_reactions_count()
        return ReactionsCount(**{k: v for k, v in counts.items() if hasattr(ReactionsCount, k)})

    @connection(
        CountedConnection[ReactionLazyType] | None,
        filterset_class=ReactionFilter,
        annotate=_metadata_annotation("_reactable_is_reactions_enabled"),
    )
    def reactions(self, info: Info) -> Iterable[Model]:
        service = shared_services.get("reactable_metadata")
        if service is not None and not service.is_reactions_enabled(self):
            return Reaction.objects.none()
        if not can_anonymous_view_reactions() and not info.context.user.is_authenticated:
            return Reaction.objects.none()
        return _reactions_for(self).order_by("-created")

    @strawberry_django.field(annotate=_metadata_annotation("_reactable_is_reactions_enabled"))
    def is_reactions_enabled(self, info: Info) -> bool:
        if service := shared_services.get("reactable_metadata"):
            return service.is_reactions_enabled(self)
        return True

    if apps.is_installed("baseapp_profiles"):

        @strawberry_django.field(graphql_type=Optional[ReactionLazyType])
        def my_reaction(self, info: Info, profile_id: strawberry.ID | None = None) -> Any:
            return _resolve_my_reaction(self, info, profile_id)

    else:

        @strawberry_django.field(graphql_type=Optional[ReactionLazyType])
        def my_reaction(self, info: Info) -> Any:
            return _resolve_my_reaction(self, info)
