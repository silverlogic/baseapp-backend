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
}
"""


def xtest_anon_cant_query_user_devices(graphql_client):
    response = graphql_client(QUERY)
    content = response.json()
    print(content)
    assert content["data"]["allUserDevices"] is None


def xtest_user_can_query_user_devices(django_user_client, graphql_user_client):
    UserDeviceFactory(user=django_user_client.user)
    response = graphql_user_client(QUERY)
    content = response.json()
    print(content)
    assert len(content["data"]["allUserDevices"]["edges"]) == 1
    assert content["data"]["allUserDevices"]["edges"][0]["node"]["address"] == "127.0.0.1"
    # assert content["data"]["allUserDevices"]["edges"][0]["node"]["deviceFamily"] == "iPhone"
    # assert content["data"]["allUserDevices"]["edges"][0]["node"]["osFamily"] == "iOS"
    # assert content["data"]["allUserDevices"]["edges"][0]["node"]["osVersion"] == "17.2"
    # assert content["data"]["allUserDevices"]["edges"][0]["node"]["browserFamily"] == "Safari"
