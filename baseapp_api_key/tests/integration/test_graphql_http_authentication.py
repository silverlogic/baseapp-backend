import pytest
from django.test import override_settings

import baseapp_api_key.tests.factories as f
from baseapp_api_key.models import APIKey
from baseapp_core.graphql.testing.fixtures import graphql_query

pytestmark = pytest.mark.django_db

ME = "{ me { email } }"


@override_settings(
    STRAWBERRY_AUTHENTICATION_CLASSES=[
        "baseapp_api_key.rest_framework.authentication.APIKeyAuthentication"
    ]
)
def test_api_key_authenticates_graphql_requests() -> None:
    api_key = f.APIKeyFactory()
    unencrypted = APIKey.objects.decrypt(encrypted_value=api_key.encrypted_api_key)

    response = graphql_query(ME, headers={"HTTP_API_KEY": unencrypted})
    assert response.json()["data"]["me"] == {"email": api_key.user.email}

    response = graphql_query(ME, headers={"HTTP_API_KEY": "BA-nonexistent-key"})
    assert response.json()["data"]["me"] is None
