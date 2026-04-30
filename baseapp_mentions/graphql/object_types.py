import graphene_django_optimizer as gql_optimizer
import swapper

from baseapp_core.graphql import DjangoObjectType
from baseapp_core.graphql import Node as RelayNode

Mention = swapper.load_model("baseapp_mentions", "Mention")


class BaseMentionObjectType:
    class Meta:
        model = Mention
        fields = ("id", "profile", "target", "created", "modified")
        interfaces = (RelayNode,)


class MentionObjectType(
    BaseMentionObjectType, gql_optimizer.OptimizedDjangoObjectType, DjangoObjectType
):
    class Meta(BaseMentionObjectType.Meta):
        pass
