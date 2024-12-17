import graphene
from baseapp_comments.graphql.mutations import CommentsMutations
from baseapp_comments.graphql.queries import CommentsQueries
from baseapp_profiles.graphql.mutations import ProfilesMutations
from baseapp_profiles.graphql.queries import ProfilesQueries
from graphene import relay
from graphene.relay.node import NodeField as RelayNodeField
from graphene_django.debug import DjangoDebug

from baseapp.activity_log.graphql.queries import ActivityLogQueries
from testproject.testapp.graphql.queries import UsersQueries


class Query(
    graphene.ObjectType, UsersQueries, ProfilesQueries, CommentsQueries, ActivityLogQueries
):
    node = RelayNodeField(relay.Node)
    debug = graphene.Field(DjangoDebug, name="_debug")


class Mutation(graphene.ObjectType, ProfilesMutations, CommentsMutations):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation)
