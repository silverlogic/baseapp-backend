import pytest
from baseapp_devices.tests.factories import UserDeviceFactory

pytestmark = pytest.mark.django_db

QUERY = """
query{
  allUserDevices {
   edges {
    node {
      address
      deviceFamily
      osFamily
      osVersion
      browserFamily
    }
  }
}
"""


def test_anon_cant_query_user_devices(graphql_client):
    response = graphql_client(QUERY)
    content = response.json()
    print(content)
    assert content["data"]["allUserDevices"] is None


def test_user_can_query_user_devices(django_user_client, graphql_user_client):
    UserDeviceFactory(user=django_user_client.user)
    UserDeviceFactory()
    response = graphql_user_client(QUERY)
    content = response.json()
    assert len(content["data"]["allUserDevices"]["edges"]) == 1
