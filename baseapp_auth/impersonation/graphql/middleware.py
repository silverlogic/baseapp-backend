import inspect
from typing import Any

from channels.db import database_sync_to_async
from graphql import GraphQLError, OperationType

from ..exceptions import ImpersonationSessionInvalid
from ..models import ImpersonationSession
from ..services import (
    SESSION_MUTATIONS,
    defer_or_record_action,
    ensure_session_active,
    get_impersonation,
    get_mutation_refusal,
    mutation_succeeded,
    record_action,
)


def check_root_mutation(session: ImpersonationSession, info) -> str | None:
    """
    The name of the root mutation to record, or None for any other root field. Raises a
    `GraphQLError` for a mutation the session may not run.
    """
    if info.operation.operation != OperationType.MUTATION:
        return None
    name = info.field_name
    if name in SESSION_MUTATIONS:
        return None
    if refusal := get_mutation_refusal(session, name):
        raise GraphQLError(str(refusal.default_detail), extensions={"code": refusal.default_code})
    return name


class ImpersonationReadOnlyMiddleware:
    """
    Graphene middleware for impersonation sessions.

    On each root field of a request made during a session it:

    - sets `user.impersonation` on `info.context.user` when that user is the session's target;
    - refuses denylisted root mutations (code `impersonation_forbidden`) and, in a read-only
      session, root mutations other than `impersonationEnd` and the allowlisted ones (code
      `impersonation_read_only`);
    - records every root mutation that runs as an `ImpersonationAction`, with whether it
      succeeded. Over HTTP the record is written by `ImpersonationMiddleware` once the
      response is ready, so a mutation whose transaction rolls back is still recorded.

    The session itself is found and validated by `ImpersonationMiddleware` (or a JWT
    authentication class using `ImpersonationJWTAuthenticationMixin`). Operations sent over a
    WebSocket are handled by `ImpersonationWebsocketGraphqlMiddleware`.
    """

    def resolve(self, next, root, info, **kwargs) -> Any:
        if info.path.prev is not None:
            return next(root, info, **kwargs)

        request = info.context
        session = get_impersonation(request)
        if session is None:
            return next(root, info, **kwargs)

        user = getattr(request, "user", None)
        if user is not None and getattr(user, "pk", None) == session.target_id:
            user.impersonation = session

        name = check_root_mutation(session, info)
        if name is None:
            return next(root, info, **kwargs)

        fields = {
            "method": getattr(request, "method", "") or "",
            "path": getattr(request, "path", "") or "",
            "operation_name": name,
        }
        try:
            result = next(root, info, **kwargs)
        except Exception:
            defer_or_record_action(request, session, succeeded=False, **fields)
            raise
        defer_or_record_action(request, session, succeeded=mutation_succeeded(result), **fields)
        return result


# The `method` of actions recorded for WebSocket operations.
WEBSOCKET_METHOD = "WS"


def _check_websocket_root_field(
    scope: dict, session: ImpersonationSession, info
) -> tuple[ImpersonationSession, str | None]:
    try:
        session = ensure_session_active(session)
    except ImpersonationSessionInvalid as exc:
        raise GraphQLError(exc.message, extensions={"code": exc.default_code})
    scope["impersonation"] = session
    if (user := scope.get("user")) is not None:
        user.impersonation = session
    return session, check_root_mutation(session, info)


class ImpersonationWebsocketGraphqlMiddleware:
    """
    GraphQL middleware for operations sent over a WebSocket during a session, which never run
    `GRAPHENE["MIDDLEWARE"]`. BaseApp's consumers (`baseapp_core.graphql.consumers`) add it
    through the `graphql_ws.middleware` shared service; a consumer of your own lists it last
    in its `middleware`.

    On each root field it re-checks the session, so a session that ended after the connection
    opened gets `impersonation_ended` errors. It refuses and records root mutations as
    `ImpersonationReadOnlyMiddleware` does, with method `WS` and the connection's path.
    """

    async def resolve(self, next, root, info, **kwargs) -> Any:
        scope = getattr(info.context, "channels_scope", None)
        session = get_impersonation(scope) if scope and info.path.prev is None else None
        if session is None:
            return await _resolved(next(root, info, **kwargs))

        session, name = await database_sync_to_async(_check_websocket_root_field)(
            scope, session, info
        )
        if name is None:
            return await _resolved(next(root, info, **kwargs))

        fields = {"method": WEBSOCKET_METHOD, "path": scope.get("path", ""), "operation_name": name}
        try:
            result = await _resolved(next(root, info, **kwargs))
        except Exception:
            await database_sync_to_async(record_action)(session, succeeded=False, **fields)
            raise
        await database_sync_to_async(record_action)(
            session, succeeded=mutation_succeeded(result), **fields
        )
        return result


async def _resolved(result: Any) -> Any:
    return await result if inspect.isawaitable(result) else result
