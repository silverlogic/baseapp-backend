import strawberry
import swapper
from django.apps import apps
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError
from strawberry import UNSET
from strawberry.types import Info

from baseapp_core.graphql import get_obj_from_relay_id, get_pk_from_relay_id
from baseapp_core.models import DocumentId
from baseapp_core.strawberry import (
    RelayMutationInput,
    RelayMutationPayload,
    relay_mutation,
)
from baseapp_core.strawberry.connections import Edge, offset_to_cursor

from .interfaces import RatingsInterface
from .types import RateLazyType

RateModel = swapper.load_model("baseapp_ratings", "Rate")


def _permission_error() -> GraphQLError:
    return GraphQLError(
        str(_("You don't have permission to perform this action")),
        extensions={"code": "permission_required"},
    )


@strawberry.input(name="RateCreateInput")
class RateCreateInput(RelayMutationInput):
    target_object_id: strawberry.ID
    value: int
    if apps.is_installed("baseapp_profiles"):
        profile_id: strawberry.ID | None = UNSET


@strawberry.type(name="RateCreatePayload")
class RateCreatePayload(RelayMutationPayload):
    rate: Edge[RateLazyType] | None = None
    target: RatingsInterface | None = None


@strawberry.type
class RatingsMutations:
    @relay_mutation(login_required=True)
    def rate_create(self, info: Info, input: RateCreateInput) -> RateCreatePayload | None:
        user = info.context.user
        has_profiles = apps.is_installed("baseapp_profiles")
        target = get_obj_from_relay_id(info, input.target_object_id)

        if not user.has_perm("baseapp_ratings.add_rate", target):
            raise _permission_error()

        profile = None
        if has_profiles:
            Profile = swapper.load_model("baseapp_profiles", "Profile")
            profile_id = getattr(input, "profile_id", None)
            profile_pk = get_pk_from_relay_id(profile_id) if profile_id else None
            if profile_pk:
                profile = Profile.objects.get_if_member(user, pk=profile_pk)
                if not user.has_perm("baseapp_ratings.add_rate_with_profile", profile):
                    raise _permission_error()
            else:
                profile = user.current_profile

        max_value = getattr(settings, "BASEAPP_MAX_RATING_VALUE", False)
        if max_value and input.value > max_value:
            raise GraphQLError(
                str(_("The maximum rating value is {0}").format(max_value)),
                extensions={"code": "max_rating_value"},
            )

        rate_create_kwargs = dict(
            user=user,
            target_document=DocumentId.get_or_create_for_object(target),
            value=input.value,
        )
        if has_profiles:
            rate_create_kwargs["profile"] = profile

        rate = RateModel.objects.create(**rate_create_kwargs)

        target.refresh_from_db()

        return RateCreatePayload(rate=Edge(node=rate, cursor=offset_to_cursor(0)), target=target)
