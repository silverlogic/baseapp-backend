import graphene
import swapper
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError
from graphql_relay.connection.arrayconnection import offset_to_cursor

from baseapp_core.graphql import (
    RelayMutation,
    get_obj_from_relay_id,
    get_pk_from_relay_id,
    login_required,
)

from .object_types import RatingsInterface

RateModel = swapper.load_model("baseapp_ratings", "Rate")
Profile = swapper.load_model("baseapp_profiles", "Profile")
RatingObjectType = RateModel.get_graphql_object_type()


class RateCreate(RelayMutation):
    rate = graphene.Field(RatingObjectType._meta.connection.Edge, required=False)
    target = graphene.Field(RatingsInterface)

    class Input:
        target_object_id = graphene.ID(required=True)
        profile_id = graphene.ID(required=False)
        value = graphene.Int(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        target = get_obj_from_relay_id(info, input.get("target_object_id"))
        target_content_type = ContentType.objects.get_for_model(target)

        if not info.context.user.has_perm("baseapp_ratings.add_rate", target):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        profile_pk = get_pk_from_relay_id(input.get("profile_id"))
        if profile_pk:
            profile = Profile.objects.get_if_member(info.context.user, pk=profile_pk)
            if not info.context.user.has_perm("baseapp_ratings.add_rate_with_profile", profile):
                raise GraphQLError(
                    str(_("You don't have permission to perform this action")),
                    extensions={"code": "permission_required"},
                )
        else:
            profile = info.context.user.current_profile

        if getattr(settings, "BASEAPP_MAX_RATING_VALUE", False):
            if input["value"] > settings.BASEAPP_MAX_RATING_VALUE:
                raise GraphQLError(
                    str(
                        _("The maximum rating value is {0}").format(
                            settings.BASEAPP_MAX_RATING_VALUE
                        )
                    ),
                    extensions={"code": "max_rating_value"},
                )

        rate = RateModel.objects.create(
            user=info.context.user,
            profile=profile,
            target_object_id=target.pk,
            target_content_type=target_content_type,
            value=input["value"],
        )

        target.refresh_from_db()

        return RateCreate(
            rate=RatingObjectType._meta.connection.Edge(node=rate, cursor=offset_to_cursor(0)),
            target=target,
        )


class RatingsMutations(object):
    rate_create = RateCreate.Field()
