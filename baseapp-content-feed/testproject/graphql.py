import graphene
from baseapp_auth.graphql.queries import UsersQueries
from baseapp_core.graphql import DeleteNode
from baseapp_profiles.graphql.queries import ProfilesQueries
from graphene import relay

from baseapp_content_feed.graphql.mutations import ContentFeedMutations
from baseapp_content_feed.graphql.queries import ContentFeedQueries


class Query(graphene.ObjectType, ContentFeedQueries, UsersQueries, ProfilesQueries):
    node = relay.node.NodeField(relay.Node)


class Mutation(
    graphene.ObjectType,
    ContentFeedMutations,
):
    delete_node = DeleteNode.Field()


schema = graphene.Schema(query=Query, mutation=Mutation)
