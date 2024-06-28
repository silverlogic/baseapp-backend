import graphene
import swapper
from baseapp_core.graphql import RelayMutation, login_required
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError
from graphql_relay.connection.arrayconnection import offset_to_cursor

from .object_types import RatingObjectType, RatingsInterface

from baseapp_core.graphql import RelayMutation, get_obj_from_relay_id, login_required

RateModel = swapper.load_model("baseapp_ratings", "Rate")


class CreateRate(RelayMutation):
    rate = graphene.Field(RatingObjectType._meta.connection.Edge, required=False)
    target = graphene.Field(RatingsInterface)

    class Input:
        target_object_id = graphene.ID(required=True)
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
            target_object_id=target.pk,
            target_content_type=target_content_type,
            value=input["value"],
        )

        target.refresh_from_db()

        return CreateRate(
            rate=RatingObjectType._meta.connection.Edge(node=rate, cursor=offset_to_cursor(0)),
            target=target,
        )


class RatingsMutations(object):
    create_rate = CreateRate.Field()
