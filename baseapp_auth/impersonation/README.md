# BaseApp Auth: Impersonation

Lets an authorized user (the *impersonator*) act as another user (the *target*) for a limited
time, with a reason, so support staff can see — and, when the project allows it, do — what the
target sees.

- A session lasts `BASEAPP_AUTH_IMPERSONATION_TTL` (one hour by default), needs a reason, and
  is stored as an `ImpersonationSession`.
- **Read-only by default.** With `BASEAPP_AUTH_IMPERSONATION_READ_ONLY = False` the session can
  *act as* the target: writes go through, and every one is recorded as an
  `ImpersonationAction`.
- Who may impersonate whom is decided by a project hook. By default superusers may impersonate
  anyone who is not a superuser.
- Ending a session revokes its tokens at once, over HTTP and WebSockets. Across processes this
  needs a shared default cache (see [Caching](#caching)).
- Signals let the project keep its own audit trail or notify the target.

The app is off unless it is in `INSTALLED_APPS`, so projects that don't install it see no
change.

## Installation

```python
INSTALLED_APPS = [
    ...
    "baseapp_auth",
    "baseapp_auth.impersonation",
]
```

Run `migrate` to create the session and action tables.

The plugin contributes a Django middleware, a Graphene middleware, a permissions backend, the
GraphQL mutations and the default settings. Slot them in where your settings assemble those
lists:

```python
MIDDLEWARE += [
    *plugin_registry.get("MIDDLEWARE", "baseapp_impersonation"),
]

GRAPHENE["MIDDLEWARE"] = (
    # Graphene runs the last-listed middleware first: list this before your
    # authentication middleware so it runs after it.
    *plugin_registry.get("GRAPHENE__MIDDLEWARE", "baseapp_impersonation"),
    *GRAPHENE["MIDDLEWARE"],
)

AUTHENTICATION_BACKENDS = [
    # First: it refuses permissions, and Django stops at the first refusal.
    *plugin_registry.get("AUTHENTICATION_BACKENDS", "baseapp_impersonation"),
    "django.contrib.auth.backends.ModelBackend",
    ...
]

SIMPLE_JWT = {
    ...
    "TOKEN_REFRESH_SERIALIZER": (
        "baseapp_auth.impersonation.serializers.ImpersonationJwtRefreshSerializer"
    ),
}
```

`python manage.py check` warns (`baseapp_impersonation.W001`–`W004`) when a piece is missing,
and `check --deploy` warns (`W005`) when sessions are cached per process.

Nothing needs wiring for WebSockets: BaseApp's GraphQL consumers pick the app up on their own
(see [WebSockets](#websockets)).

Without the plugin registry, the paths are:

| Setting | Entry |
|---|---|
| `MIDDLEWARE` | `baseapp_auth.impersonation.middleware.ImpersonationMiddleware` |
| `GRAPHENE["MIDDLEWARE"]` | `baseapp_auth.impersonation.graphql.middleware.ImpersonationReadOnlyMiddleware` |
| `AUTHENTICATION_BACKENDS` | `baseapp_auth.impersonation.permissions.ImpersonationPermissionsBackend` |
| GraphQL mutations | `baseapp_auth.impersonation.graphql.mutations.ImpersonationMutations` |

The user type gets its `impersonation` field from the `ImpersonationInterface` shared
interface, which `baseapp_auth`'s `UserObjectType` already lists. A project with its own user
type adds `"ImpersonationInterface"` to its `graphql_shared_interfaces.get(...)` list.

## How it works

`impersonationStart` returns a token pair for the target, built by your
`TOKEN_OBTAIN_SERIALIZER` (so it carries the same claims as a login) plus two claims:

| Claim | Value |
|---|---|
| `imp` | the impersonator's pk |
| `imp_sid` | the session's pk |

The refresh token's `exp` is the session's expiry, and no access token outlives it.

Every request that carries such a token is checked against its session (cached for
`BASEAPP_AUTH_IMPERSONATION_CACHE_TIMEOUT` seconds; ending a session clears the cache):

- `ImpersonationMiddleware` reads the Bearer token of every HTTP request, whatever
  authentication class the view uses. A token of an ended, expired or revoked session gets
  `401 {"detail": ..., "code": "impersonation_ended"}`. In a read-only session an unsafe REST
  request gets `403 {"detail": ..., "code": "impersonation_read_only"}`.
- `ImpersonationReadOnlyMiddleware` handles GraphQL, where every request is a POST: in a
  read-only session it refuses root mutations with error code `impersonation_read_only`.
  `impersonationEnd` is always allowed.
- Writes on `BASEAPP_AUTH_IMPERSONATION_DENYLIST` are refused in every session, even when acting
  as the user, with code `impersonation_forbidden` (403 over REST). By default it holds
  BaseApp's account-security endpoints — change password, delete account, change email, MFA —
  which an impersonator must never use.
- SimpleJWT's refresh, verify and blacklist (logout) views are always allowed and never
  recorded, also when the client sends its Bearer header with them. The login action is not.
- The refresh serializer refuses to refresh a token of an ended session.
- A session whose impersonator is deactivated or deleted is revoked on its next request.
- WebSocket connections are checked too, on connect and on every operation (see
  [WebSockets](#websockets)).

The client keeps its own tokens aside while the session runs and puts them back after
`impersonationEnd` (the BaseApp frontend's `useStartImpersonation` / `useEndImpersonation`
do this).

### Act-as mode and the audit trail

Every write that runs during a session — an unsafe REST request or a GraphQL root mutation,
over HTTP or a WebSocket, in either mode — is stored as an `ImpersonationAction`:

| Field | Value |
|---|---|
| `session` | the session |
| `created` | when |
| `method`, `path` | the HTTP request; `WS` and the connection's path for a WebSocket |
| `operation_name` | the GraphQL mutation (e.g. `commentCreate`); empty for REST |
| `status_code` | the HTTP status of a REST write; empty for GraphQL |
| `succeeded` | a REST status below 400, or a mutation that raised no error and returned no `errors` |

HTTP writes are recorded after the response, outside the request's transaction, so a write that
failed or rolled back is recorded too. The Django admin lists sessions with their actions, and
staff with the change permission can revoke running sessions there.

Sessions and their actions are an audit trail: deleting the impersonator's account keeps them,
with an empty `impersonator`. Deleting the target's account deletes them with the rest of the
target's data.

## GraphQL

```graphql
mutation {
  impersonationStart(input: { targetUser: "<user id>", reason: "Ticket 1234" }) {
    access
    refresh
    session { id expiresAt readOnly target { id fullName } }
  }
}

mutation {
  # Inside the session: ends it. From the impersonator's own account, pass `session`.
  impersonationEnd(input: {}) {
    session { id isActive endReason }
  }
}

query {
  me {
    impersonation {  # null outside a session
      impersonator { id fullName }
      startedAt
      expiresAt
      readOnly
    }
  }
}
```

Error codes: `permission_required` (the rules refuse the pair), `invalid_input` (no reason),
`not_found`, `impersonation_active` (starting a session from inside one),
`impersonation_read_only`, `impersonation_forbidden`, and `impersonation_ended` (an operation on
a WebSocket whose session has ended).

`ImpersonationSession` is a Relay node. A user sees the sessions they started and the one
their request belongs to; holders of `baseapp_impersonation.view_impersonationsession` see all.
Holders of `baseapp_impersonation.change_impersonationsession` can end anyone's session (it is
recorded as revoked).

## Settings

| Setting | Default | |
|---|---|---|
| `BASEAPP_AUTH_IMPERSONATION_TTL` | `3600` | Session length, in seconds or a `timedelta`. |
| `BASEAPP_AUTH_IMPERSONATION_READ_ONLY` | `True` | `False` lets sessions act as the target. Each session keeps the mode it started with. |
| `BASEAPP_AUTH_IMPERSONATION_CAN_IMPERSONATE` | superusers, non-superuser targets | Dotted path (or callable) `(impersonator, target, request) -> bool`. |
| `BASEAPP_AUTH_IMPERSONATION_TOKEN_HOOK` | `None` | Dotted path (or callable) `(refresh, target, impersonator)`, called last; may add claims. |
| `BASEAPP_AUTH_IMPERSONATION_READ_ONLY_ALLOWLIST` | `()` | Writes a read-only session may still make: GraphQL mutation names (`"protectedFileLink"`), or regexes matched against the request path (entries starting with `/` or `^`). |
| `BASEAPP_AUTH_IMPERSONATION_DENYLIST` | BaseApp's change-password, delete-account, change-email and MFA routes under `/v1/` | Writes refused in every session, in the allowlist's format. It wins over the allowlist. Extend it with your own account-security routes and mutations; mount BaseApp's routes elsewhere and you must list their real paths. |
| `BASEAPP_AUTH_IMPERSONATION_DENIED_PERMISSIONS` | `()` | Permissions refused to the target while impersonated. |
| `BASEAPP_AUTH_IMPERSONATION_CACHE_TIMEOUT` | `30` | Seconds a session lookup is cached; `0` reads it from the database on every request. |

Whatever the hook says, both users must be active, they must be different people, and a session
can't be started from inside another one.

### Example: a project's rules

```python
# settings.py
BASEAPP_AUTH_IMPERSONATION_CAN_IMPERSONATE = "apps.support.impersonation.can_impersonate"
BASEAPP_AUTH_IMPERSONATION_TOKEN_HOOK = "apps.support.impersonation.add_claims"
BASEAPP_AUTH_IMPERSONATION_READ_ONLY = False
BASEAPP_AUTH_IMPERSONATION_DENIED_PERMISSIONS = [
    # Keep the target's private conversations out of the session (see below).
    "baseapp_chats.list_chatrooms",
    "baseapp_chats.view_chatroom",
    "baseapp_chats.view_message",
]

# apps/support/impersonation.py
def can_impersonate(impersonator, target, request) -> bool:
    return (
        impersonator.has_perm("support.impersonate_users")
        and not target.is_superuser
        and not target.has_perm("support.impersonate_users")
    )


def add_claims(refresh, target, impersonator) -> None:
    refresh["support_session"] = True
```

### Example: hiding the target's chats

`baseapp_chats` gates its queries and subscriptions on three permissions, so denying them hides
the target's chats over HTTP and WebSockets alike:

| Permission | Hides |
|---|---|
| `baseapp_chats.list_chatrooms` | `Profile.chatRooms` and `unreadMessagesCount`, and the `chatRoomOnRoomUpdate` and `chatRoomOnMessagesCountUpdate` subscriptions (which carry each room's messages) |
| `baseapp_chats.view_chatroom` | `node(id:)` for a room, and the `chatRoomOnMessage` subscription |
| `baseapp_chats.view_message` | `node(id:)` for a message |

Notifications of new messages come from `baseapp_notifications` and are not covered by these
permissions.

This hides reading only. To stop an act-as session from writing in the target's chats too, add
the chat mutations (e.g. `chatRoomSendMessage`, `chatRoomCreate`) to
`BASEAPP_AUTH_IMPERSONATION_DENYLIST`.

## Hooks for project code

- `get_impersonation(obj=None)` returns the active `ImpersonationSession` for a request, a
  GraphQL `info.context`, an ASGI scope or a user — or, with no argument, for the request being
  served. `is_impersonated(obj=None)` is its boolean. Use them to hide or change anything else
  during a session, e.g. in a permissions backend, a queryset or a resolver.
- `ImpersonationPermissionsBackend` refuses `BASEAPP_AUTH_IMPERSONATION_DENIED_PERMISSIONS`,
  over HTTP and WebSockets. Django grants every permission to an active superuser before asking
  any backend.
- Signals, all from `baseapp_auth.impersonation.signals`:

  | Signal | Arguments |
  |---|---|
  | `impersonation_started` | `session`, `request` |
  | `impersonation_ended` | `session`, `reason`, `request` (`None` when found expired or revoked) |
  | `impersonation_denied` | `impersonator`, `target`, `request` |
  | `impersonation_action` | `action`, `session`, `request` |

- Services in `baseapp_auth.impersonation.services`: `start_impersonation(impersonator,
  target, reason, request=None) -> (session, refresh)`, `end_impersonation(session, reason,
  request=None)`, `can_impersonate(...)`, and `check_impersonation(request_or_scope, token)`
  for custom authentication code.

### Custom JWT authentication

`ImpersonationMiddleware` covers HTTP requests whatever authenticates them. Code that
authenticates tokens elsewhere can check the session itself:

```python
from baseapp_auth.impersonation.authentication import ImpersonationJWTAuthenticationMixin


class MyJWTAuthentication(ImpersonationJWTAuthenticationMixin, JWTAuthentication):
    ...
```

The mixin also sets `user.impersonation` on the authenticated user, and
`ImpersonationJWTAuthentication` is a ready-made SimpleJWT class with it. A custom refresh
serializer mixes in `ImpersonationRefreshSerializerMixin`.

### WebSockets

BaseApp's WebSocket authentication (`baseapp_core.authentication`, used by
`GraphqlWsJWTAuthenticatedConsumer` from the `connection_init` payload and by
`baseapp_core.channels.JWTAuthMiddleware` from the subprotocols) asks the app about every
token through the `auth.jwt_token_check` shared service. So, with no wiring:

- a token, or a refresh token, of an ended session authenticates nobody: the connection stays
  anonymous and no new access token is minted;
- the connection's user carries `user.impersonation`, so `get_impersonation(scope)`,
  `is_impersonated(user)` and `DENIED_PERMISSIONS` work in subscriptions and resolvers.

WebSocket operations never run `GRAPHENE["MIDDLEWARE"]`. BaseApp's GraphQL consumers add
`ImpersonationWebsocketGraphqlMiddleware` through the `graphql_ws.middleware` shared service. On
every operation it re-checks the session, so one ended after the connection opened gets
`impersonation_ended` errors, and it refuses and records mutations exactly as over HTTP. A
consumer of your own that does not extend BaseApp's adds it last in its `middleware`:

```python
from baseapp_auth.impersonation.graphql.middleware import ImpersonationWebsocketGraphqlMiddleware


class MyConsumer(channels_graphql_ws.GraphqlWsConsumer):
    middleware = [threadpool_for_sync_resolvers, ImpersonationWebsocketGraphqlMiddleware()]
```

To close a connection opened with an ended session instead of leaving it anonymous, wrap
`ImpersonationWebsocketMiddleware` inside `JWTAuthMiddleware`:

```python
JWTAuthMiddleware(ImpersonationWebsocketMiddleware(URLRouter(...)))
```

A consumer that writes outside GraphQL should check `get_impersonation(scope)` itself.

### Caching

Session lookups are cached for `BASEAPP_AUTH_IMPERSONATION_CACHE_TIMEOUT` seconds in the
default cache, and ending a session clears the entry. With Django's default `LocMemCache`
each process has its own copy, so other processes keep accepting an ended session's tokens
for up to that long. Use a shared cache (e.g. Redis) in production, or set the timeout to `0`.
`manage.py check --deploy` warns about this (`baseapp_impersonation.W005`).
