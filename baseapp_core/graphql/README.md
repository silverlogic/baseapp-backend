# Baseapp Core GraphQL

## How to install

Run `pip install baseapp-backend[graphql]`
And make sure to add the frozen version to your `requirements/base.txt` file

## Setup

1. Make sure to add `graphene_django` to `INSTALLED_APPS`.
2. Add `GRAPHENE` to your `settings/base.py`:

```python
# GraphQL
GRAPHENE = {
    "SCHEMA": "apps.graphql.schema",
    "MIDDLEWARE": (
        "graphene_django.debug.DjangoDebugMiddleware",
        "baseapp_core.graphql.LogExceptionMiddleware",
        "baseapp_core.graphql.TokenAuthentication",
    ),
    "SCHEMA_OUTPUT": "schema.graphql",
}
```

3. Create file `apps/graphql.py` with:

```python
import graphene
from baseapp_auth.graphql import UsersQuery
from graphene_django.debug import DjangoDebug

class Query(
    graphene.ObjectType,
    UsersQuery
):
    debug = graphene.Field(DjangoDebug, name="_debug")

schema = graphene.Schema(query=Query)
```

4. Add the path in your `urls.py`

```python
from baseapp_core.graphql import GraphQLView
from django.views.decorators.csrf import csrf_exempt


urlpatterns = [
    # ...
    path("graphql", csrf_exempt(GraphQLView.as_view(graphiql=True))),
]
```

Our `GraphQLView` is a subclass of `graphene_django.views.GraphQLView` with some additional features:
- Sentry integration, it will name the transaction with the query name instead of just `/graphql`, making it easy to find queries on Sentry.

## Enable websockets

To enable websockets you need to make sure you have `daphne` in your `INSTALLED_APPS` and `ASGI_APPLICATION` setup in your settings file.

```python
INSTALLED_APPS = [
    "daphne",
    # ...
]

ASGI_APPLICATION = "apps.asgi.application"
```

In your `asgi.py` make sure to have something like:
    
```python
from django.core.asgi import get_asgi_application
from django.urls import re_path

from channels.routing import ProtocolTypeRouter, URLRouter

django_asgi_app = get_asgi_application()

# we need to load all applications before we can import from the apps

from baseapp_core.graphql.consumers import GraphqlWsJWTAuthenticatedConsumer 

# OR if not using JWT:
# from baseapp_core.graphql.consumers import GraphqlWsAuthenticatedConsumer


application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": URLRouter([
            re_path(r"graphql", GraphqlWsJWTAuthenticatedConsumer.as_asgi())
        ]),
    }
)
```

**Make sure** to check that when running `runserver` if you see the following message, this will confirm you are using ASGI:

```
[daphne.server] [INFO] Listening on TCP address 0.0.0.0:8000
```

## Usage

### Object Types

Create your first `DjangoObjectType` in `apps/[app_name]/graphql/object_types.py`, like:

```python
from baseapp_core.graphql import DjangoObjectType

class UserNode(DjangoObjectType):
    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name")
```

ObjectTypes that inherit from `DjangoObjectType` will have the following fields:
- `id` - Relay global id, base64 of `{ObjectType}:{pk}`
- `pk` - Same as your model's primary key

All connections with this ObjectType will inherit `CountedConnection`, which will add the following fields to the connection type:
- `totalCount` - Total number of objects in the database for this query
- `edgesCount` - Number of objects in this page

And will have the same name of the model, doens't better whats the ObjectType's class name, e.g.:

```python
class MyObjectType(DjangoObjectType):
    class Meta:
        model = MyModel
```

Your GraphQL schema will have a `MyModel` type. You can still override with a `name` attribute if necessary:

```python
class MyObjectType(DjangoObjectType):
    class Meta:
        model = MyModel
        name = "MyCustomName"
```

### Mutations

Create your first mutation in `apps/[app_name]/graphql/mutations.py`, like:

```python
from baseapp_core.graphql import RelayMutation
from .object_types import UserNode

class ChangePassword(RelayMutation):
    ok = graphene.Boolean(required=True)

    class Input:
        old_password = graphene.String(required=True)
        new_password = graphene.String(required=True)


class UserMutations:
    change_password = ChangePassword.Field()
```

By inherinting `RelayMutation` your mutation will have the following fields:
- `clientMutationId` - Relay client mutation id
- `errors` - List of errors, if any
- `_debug` - Debug information, only available if `DEBUG=True`

## Utils

### RelayModel

Add `RelayModel` to your model's inheritance, like:

```python
from baseapp_core.models import RelayModel

class User(RelayModel):
    # ...
```

This will add the following methods and properties to your model:
- `relay_id` - Relay global ID property, base64 of `{ObjectType}:{pk}`
- `get_graphql_object_type` - Class method that, return the model's `DjangoObjectType` class


So you can access the relay id of your model like:

```python
user = User.objects.get(pk=1)
user.relay_id
```

### relay.Node.Field

Add `baseapp_core.graphql.relay.Node.Field` to your `Query` class, like:

```python
from baseapp_core.graphql import Node

class Query(
    graphene.ObjectType,
    UsersQuery
):
    user = Node.Field(UserObjectType)
```

This will make it possible to retrieve objects by both `relay_id` and your models's `pk`, e.g.:

```graphql
query {
    byRelayId: user(id: "VXNlcjox") {
        id
        pk
        username
    }
    byPk: user(id: "1") {
        id
        pk
        username
    }
}
```

Aboth will return the same object.

### DeleteNode

Add `baseapp_core.graphql.mutations.DeleteNode` to your `Mutation` class, like:

```python
from baseapp_core.graphql import DeleteNode

class Mutation(
    graphene.ObjectType,
):
    delete_node = DeleteNode.Field()
```

This will make it possible to delete any object that the user has permission to delete:

```graphql
mutation {
    deleteNode(id: "VXNlcjox") {
        deletedID @deleteRecord
    }
}
```

### get_obj_relay_id

Generate a relay id from a model instance, e.g.:

```python
from baseapp_core.graphql import get_obj_relay_id

user = User.objects.get(pk=1)
get_obj_relay_id(user)
```
    
### get_obj_from_relay_id

Get a model instance from a relay id, e.g.:

```python
from baseapp_core.graphql import get_obj_from_relay_id

user = get_obj_from_relay_id(info, "VXNlcjox")
```

Where `info` is an instance of `graphene.ResolveInfo` passed to your resolver.

### get_pk_from_relay_id

Get a model's pk from a relay id, e.g.:

```python
from baseapp_core.graphql import get_pk_from_relay_id

pk = get_pk_from_relay_id("VXNlcjox")
```

### ThumbnailField

Add `ThumbnailField` to your model, like:

```python
from baseapp_core.graphql import ThumbnailField

class User(RelayModel):
    selfie = ThumbnailField()
```

Then we can query by specific size, like:

```graphql
query {
    user(id: "1") {
        selfie(width: 100, height: 100) {
            url
        }
    }
}
```

### login_required

Add `login_required` to your mutation, like:

```python
from baseapp_core.graphql import login_required

class ChangePassword(RelayMutation):
    ok = graphene.Boolean(required=True)

    class Input:
        old_password = graphene.String(required=True)
        new_password = graphene.String(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        # ...
```

### get_object_type_for_model

Returns a function that will return the `DjangoObjectType` class for a model, like:

```python
import swapper
from baseapp_core.graphql import get_object_type_for_model

Profile = swapper.load_model("baseapp_profiles", "Profile")

class UserObjectType(DjangoObjectType):
    profile = graphene.Field(get_object_type_for_model(Profile))

    class Meta:
        model = User
```


## Testing

Make sure to add to your app's `confitest.py`:

```python
from baseapp_core.tests.fixtures import *  # noqa
from baseapp_core.graphql.testing.fixtures import *  # noqa
```

Then you can use the following fixtures:

### graphql_client

Args:
- `query`: (string) - GraphQL query to run
- `operation_name`: (string) - If the query is a mutation or named query, you must supply the operation_name. For annon queries ("{ ... }"), should be None (default).
- `input_data`: (dict) - If provided, the $input variable in GraphQL will be set to this value. If both `input_data` and `variables`, are provided, the `input` field in the `variables` dict will be overwritten with this value.
- `variables`: (dict) - If provided, the "variables" field in GraphQL will be set to this value.
- `headers`: (dict) - If provided, the headers in POST request to GRAPHQL_URL will be set to this value. Keys should be prepended with "HTTP_" (e.g. to specify the "Authorization" HTTP header, use "HTTP_AUTHORIZATION" as the key).
- `client`: (django.test.Client) - Test client. Defaults to django.test.Client.
- `graphql_url`: (string) - URL to graphql endpoint. Defaults to "/graphql".

Returns:
- `Response` object from client

### graphql_user_client

To make request as a user.

Args are the same as `graphql_client`, but will inject `django_user_client` as the `client` argument. 

## Testing Websockets

For testing websockets its necessary to use the following in the begining of your tests file:

```python
pytestmark = pytest.mark.django_db(transaction=True)
```

Its wise not to mix websocket tests with other tests, since it will make the tests run slower.

For testing websockets we have the following fixtures:

### graphql_ws_user_client

Args:
- `consumer_attrs`: `GraphqlWsConsumer` attributes dict. Optional.
- `communicator_kwds`: Extra keyword arguments for the Channels `channels.testing.WebsocketCommunicator`. Optional.

Example:

```python
@pytest.mark.asyncio
async def test_user_recieves_new_notification_subscription_event(
    django_user_client, graphql_ws_user_client
):
    # Establish & initialize WebSocket GraphQL connection.
    client = await graphql_ws_user_client(consumer_attrs={"strict_ordering": True})

    # Subscribe to GraphQL subscription.
    sub_id = await client.send(
        msg_type="subscribe",
        payload={
            "query": SUBSCRIPTION_QUERY,
            "operationName": "op_name",
        },
    )
    await client.assert_no_messages()

    notification = await database_sync_to_async(NotificationFactory)(
        recipient=django_user_client.user
    )

    # Check that subscription message were sent.
    resp = await client.receive(assert_id=sub_id, assert_type="next")
    assert (
        resp["data"]["onNotificationChange"]["createdNotification"]["node"]["id"]
        == notification.relay_id
    )

    # Disconnect and wait the application to finish gracefully.
    await client.finalize()
```

### graphql_websocket

Same as `graphql_ws_user_client`, but as an anonymous user.
