import graphene

from baseapp_notifications.graphql.mutations import NotificationsMutations
from baseapp_notifications.graphql.subscriptions import NotificationsSubscription
from testproject.testapp.graphql.queries import UsersQuery


class Query(
    graphene.ObjectType,
    UsersQuery,
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
