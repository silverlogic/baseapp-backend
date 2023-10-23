import graphene
import graphene_django_optimizer as gql_optimizer
import swapper
from baseapp_core.graphql import DjangoObjectType
from django.contrib.contenttypes.models import ContentType
from graphene import relay
from graphene_django.filter import DjangoFilterConnectionField

Reaction = swapper.load_model("baseapp_reactions", "Reaction")

ReactionTypesEnum = graphene.Enum.from_enum(Reaction.ReactionTypes)


def create_object_type_from_enum(name, enum):
    fields = {}
    for reaction_type in enum:
        fields[reaction_type.name] = graphene.Int()
    fields["total"] = graphene.Int()
    return type(name, (graphene.ObjectType,), fields)


ReactionsCount = create_object_type_from_enum("ReactionsCount", Reaction.ReactionTypes)


class ReactionsNode(relay.Node):
    reactions_count = graphene.Field(ReactionsCount)
    reactions = DjangoFilterConnectionField(lambda: ReactionNode)
    my_reaction = graphene.Field(lambda: ReactionNode, required=False)

    def resolve_reactions(self, info, **kwargs):
        target_content_type = ContentType.objects.get_for_model(self)
        return Reaction.objects.filter(
            target_content_type=target_content_type,
            target_object_id=self.pk,
        ).order_by("-created")

    def resolve_my_reaction(self, info, **kwargs):
        if info.context.user.is_authenticated:
            target_content_type = ContentType.objects.get_for_model(self)
            return Reaction.objects.filter(
                target_content_type=target_content_type,
                target_object_id=self.pk,
                user=info.context.user,
            ).first()


class ReactionNode(DjangoObjectType):
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
    def get_queryset(cls, queryset, info):
        return gql_optimizer.query(queryset, info)
