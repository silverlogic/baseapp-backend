import graphene
from baseapp_auth.graphql.queries import UsersQueries

from baseapp_notifications.graphql.mutations import NotificationsMutations
from baseapp_notifications.graphql.subscriptions import NotificationsSubscription


class Query(
    graphene.ObjectType,
    UsersQueries,
):
    pass


class Mutation(
    graphene.ObjectType,
    NotificationsMutations,
):
    pass


class Subscription(graphene.ObjectType, NotificationsSubscription):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation, subscription=Subscription)
