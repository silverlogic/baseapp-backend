# Baseapp Core GraphQL helpers

GraphQL is served by Strawberry (`strawberry-graphql` + `strawberry-graphql-django`); the layer
lives in `baseapp_core.strawberry` (`django_type`, `type_for_model`, `Node`, `connection`,
`CountedConnection`, `relay_mutation`, subscriptions, `build_schema`, `GraphQLView`,
`GraphQLWSConsumer`). Patterns: `docs/strawberry-porting-guide.md`.

`baseapp_core.graphql` keeps the framework-independent helpers: `RelayModel`, relay-id utilities and
the GraphQL test fixtures.

## Serving the schema

```python
# apps/graphql.py
from baseapp_auth.strawberry.queries import UsersQueries
from baseapp_core.plugins import plugin_registry
from baseapp_core.strawberry.schema import build_schema

schema = build_schema(
    queries=[UsersQueries, *plugin_registry.get_all_strawberry_queries()],
    mutations=plugin_registry.get_all_strawberry_mutations(),
    subscriptions=plugin_registry.get_all_strawberry_subscriptions(),
    types=plugin_registry.get_all_strawberry_types(),
)
```

```python
# settings
STRAWBERRY_SCHEMA = "apps.graphql.schema"
STRAWBERRY_AUTHENTICATION_CLASSES = [
    "rest_framework_simplejwt.authentication.JWTAuthentication",
]
```

```python
# urls.py
from baseapp_core.strawberry.views import GraphQLView

urlpatterns = [
    re_path(r"^graphql/?$", csrf_exempt(GraphQLView.as_view(schema=schema))),
]

# asgi.py — subscriptions over graphql-transport-ws on the same path
from baseapp_core.strawberry.subscriptions import GraphQLWSConsumer

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": URLRouter([re_path(r"^graphql/?$", GraphQLWSConsumer.as_asgi(schema=schema))]),
})
```

`GraphQLView` makes `info.context` the Django request (resolvers read `info.context.user`),
authenticates with `STRAWBERRY_AUTHENTICATION_CLASSES` and accepts multipart uploads.
`GraphQLWSConsumer` authenticates from `connectionParams` (`Authorization`, `Refresh`,
`Current-Profile`), unless an ASGI middleware already set `scope["user"]`. It never reads
cookies, so it accepts WebSocket handshakes from any origin; set
`STRAWBERRY_WS_ALLOWED_ORIGINS = ["https://app.example.com"]` to restrict them (Strawberry
refuses cross-origin browser handshakes by default), and always do so when wrapping the consumer
in a cookie-based auth middleware.

Custom scalars (`JSONString`, `GenericScalar`, `BigInt` in `baseapp_core.strawberry.scalars`) are
`NewType`s; `build_schema` adds their definitions to `StrawberryConfig.scalar_map`.

Export the SDL with `manage.py graphql_schema --out schema.graphql`; `--check` fails when the
committed file differs.

## RelayModel

```python
from baseapp_core.graphql import RelayModel

class Comment(RelayModel):
    ...
```

Adds `relay_id`, the object's global id (public id or `Type:pk`, per the hashids strategy) under
the GraphQL type registered for the model, so project overrides are honoured:

```python
comment.relay_id
```

## Relay-id utilities

```python
from baseapp_core.graphql import (
    get_obj_from_relay_id,
    get_obj_relay_id,
    get_pk_from_relay_id,
    resolve_document_content_object,
)

get_obj_relay_id(comment)               # same as comment.relay_id
get_pk_from_relay_id(relay_id)          # pk from a public id, pk or legacy global id
get_obj_from_relay_id(info, relay_id)   # instance, through the strategy
resolve_document_content_object(document, info)  # DocumentId.content_object, cached per request
```

Inside Strawberry resolvers, `baseapp_core.strawberry.relay.get_instance_from_global_id(info, id)`
does the same lookup through the schema's types.

## Testing

Add to your app's `conftest.py`:

```python
from baseapp_core.tests.fixtures import *  # noqa
from baseapp_core.graphql.testing.fixtures import *  # noqa
```

### graphql_client / graphql_user_client

`graphql_client(query, operation_name=None, input_data=None, variables=None, headers=None, ...)`
posts to `/graphql` and returns the response. `graphql_user_client` does the same as
`django_user_client.user`.

- `input_data`: sets `$input` (overrides `variables["input"]`).
- `headers`: keys prefixed with `HTTP_` (`HTTP_AUTHORIZATION`).
- `content_type="multipart/form-data"` plus `extra={...}` to post files next to the operation.
- `graphql_url`: defaults to `/graphql`.

### graphql_client_with_queries

Returns `(response, queries)`; `queries.count` and `queries.log` describe every SQL query the
request ran. Use it for query-count regression tests.

### graphql_ws_user_client

Factory of graphql-transport-ws communicators authenticated as `django_user_client.user` (JWT and
`Current-Profile`, like the frontend):

```python
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.asyncio
async def test_receives_notification(django_user_client, graphql_ws_user_client):
    async with await graphql_ws_user_client() as ws:
        result = next_result(ws, SUBSCRIPTION)
        await wait_for_group(subscription_group("OnNotificationChange", django_user_client.user.pk))
        await database_sync_to_async(NotificationFactory)(recipient=django_user_client.user)
        payload = await result

    assert payload.errors is None
    assert payload.data["onNotificationChange"]["createdNotification"]["node"]["id"]
```

`next_result`, `wait_for_group` and `ws_communicator` (anonymous or any user) are in
`baseapp_core.strawberry.testing`. Keep websocket tests in their own modules: they need
transactional tests.
