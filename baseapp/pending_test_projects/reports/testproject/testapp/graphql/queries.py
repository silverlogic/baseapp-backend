from baseapp_auth.graphql.queries import get_user_queries

from .object_types import UserNode

UsersQueries = get_user_queries(UserNode)
