from baseapp_core.graphql.testing.fixtures import graphql_query
from baseapp_core.tests.factories import UserFactory
from baseapp_core.tests.fixtures import DjangoClient


class GraphqlHelper:
    _django_user_client = None

    def query(self, *args, **kwargs):
        return graphql_query(*args, **kwargs, client=self.django_user_client())

    def django_user_client(self):
        if self._django_user_client is None:
            self._django_user_client = user = UserFactory()
            client = DjangoClient()
            client.force_login(user)
            self._django_user_client = client
        return self._django_user_client
