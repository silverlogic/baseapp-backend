import graphene
from baseapp_profiles.graphql.queries import ProfilesQueries

from baseapp_chats.graphql.mutations import ChatsMutations
from baseapp_chats.graphql.queries import ChatsQueries
from baseapp_chats.graphql.subscriptions import ChatsSubscriptions
from testproject.testapp.graphql.queries import UsersQueries


class Query(graphene.ObjectType, UsersQueries, ProfilesQueries, ChatsQueries):
    pass


class Mutation(
    graphene.ObjectType,
    ChatsMutations,
):
    pass


class Subscription(graphene.ObjectType, ChatsSubscriptions):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation, subscription=Subscription)
