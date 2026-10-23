from typing import Any

from graphql import GraphQLError, OperationType

from ..services import (
    SESSION_MUTATIONS,
    defer_or_record_action,
    get_impersonation,
    get_mutation_refusal,
)


class ImpersonationReadOnlyMiddleware:
    """
    Graphene middleware for impersonation sessions.

    On each root field of a request made during a session it:

    - sets `user.impersonation` on `info.context.user` when that user is the session's target;
    - refuses denylisted root mutations (code `impersonation_forbidden`) and, in a read-only
      session, root mutations other than `impersonationEnd` and the allowlisted ones (code
      `impersonation_read_only`);
    - records every root mutation that runs as an `ImpersonationAction`. Over HTTP the
      record is written by `ImpersonationMiddleware` once the response is ready, so a
      mutation whose transaction rolls back is still recorded.

    The session itself is found and validated by `ImpersonationMiddleware` (or a JWT
    authentication class using `ImpersonationJWTAuthenticationMixin`).
    """

    def resolve(self, next, root, info, **kwargs) -> Any:
        if info.path.prev is None:
            self.check_root_field(info)
        return next(root, info, **kwargs)

    @staticmethod
    def check_root_field(info) -> None:
        request = info.context
        session = get_impersonation(request)
        if session is None:
            return

        user = getattr(request, "user", None)
        if user is not None and getattr(user, "pk", None) == session.target_id:
            user.impersonation = session

        if info.operation.operation != OperationType.MUTATION:
            return
        name = info.field_name
        if name in SESSION_MUTATIONS:
            return
        if refusal := get_mutation_refusal(session, name):
            raise GraphQLError(
                str(refusal.default_detail), extensions={"code": refusal.default_code}
            )
        defer_or_record_action(
            request,
            session,
            method=getattr(request, "method", "") or "",
            path=getattr(request, "path", "") or "",
            operation_name=name,
        )
