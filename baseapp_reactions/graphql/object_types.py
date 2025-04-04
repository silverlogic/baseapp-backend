import graphene
import graphene_django_optimizer as gql_optimizer
import swapper
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from graphene import relay
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.graphql import (
    DjangoObjectType,
    get_object_type_for_model,
    get_pk_from_relay_id,
)

Reaction = swapper.load_model("baseapp_reactions", "Reaction")
Profile = swapper.load_model("baseapp_profiles", "Profile")

ReactionTypesEnum = graphene.Enum.from_enum(Reaction.ReactionTypes)


def create_object_type_from_enum(name, enum):
    fields = {}
    for reaction_type in enum:
        fields[reaction_type.name] = graphene.Int()
    fields["total"] = graphene.Int()
    return type(name, (graphene.ObjectType,), fields)


ReactionsCount = create_object_type_from_enum("ReactionsCount", Reaction.ReactionTypes)


class ReactionsInterface(relay.Node):
    reactions_count = graphene.Field(ReactionsCount)
    reactions = DjangoFilterConnectionField(get_object_type_for_model(Reaction))
    is_reactions_enabled = graphene.Boolean(required=True)
    my_reaction = graphene.Field(
        get_object_type_for_model(Reaction),
        required=False,
        profile_id=graphene.ID(required=False),
    )

    def resolve_reactions(self, info, **kwargs):
        if not getattr(self, "is_reactions_enabled", True):
            return Reaction.objects.none()

        CAN_ANONYMOUS_VIEW_REACTIONS = getattr(
            settings, "BASEAPP_REACTIONS_CAN_ANONYMOUS_VIEW_REACTIONSS", True
        )
        if not CAN_ANONYMOUS_VIEW_REACTIONS and not info.context.user.is_authenticated:
            return Reaction.objects.none()

        target_content_type = ContentType.objects.get_for_model(self)
        return Reaction.objects.filter(
            target_content_type=target_content_type,
            target_object_id=self.pk,
        ).order_by("-created")

    def resolve_my_reaction(self, info, profile_id=None, **kwargs):
        if info.context.user.is_authenticated:
            if profile_id:
                pk = get_pk_from_relay_id(profile_id)
                profile = Profile.objects.get_if_member(pk=pk, user=info.context.user)
            else:
                profile = info.context.user.current_profile
            if not profile:
                return None
            return Reaction.objects.filter(
                target_content_type=ContentType.objects.get_for_model(self),
                target_object_id=self.pk,
                profile_id=profile.pk,
            ).first()


class BaseReactionObjectType:
    target = graphene.Field(relay.Node)
    reaction_type = graphene.Field(ReactionTypesEnum)

    class Meta:
        interfaces = (relay.Node,)
        model = Reaction
        fields = (
            "id",
            "user",
            "reaction_type",
            "created",
            "modified",
            "target",
        )
        filter_fields = {
            "id": ["exact"],
        }

    @classmethod
    def get_node(self, info, id):
        node = super().get_node(info, id)
        if not info.context.user.has_perm("baseapp_comments.view_comment", node):
            return None
        return node


class ReactionObjectType(
    BaseReactionObjectType, gql_optimizer.OptimizedDjangoObjectType, DjangoObjectType
):
    class Meta(BaseReactionObjectType.Meta):
        pass
