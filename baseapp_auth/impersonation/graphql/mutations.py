import graphene
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError

from baseapp_core.graphql import (
    RelayMutation,
    get_obj_from_relay_id,
    get_object_type_for_model,
    login_required,
)

from ..exceptions import ImpersonationNotAllowed
from ..models import ImpersonationSession
from ..services import end_impersonation, get_impersonation, start_impersonation

User = get_user_model()


def _get_object(info, relay_id: str) -> object | None:
    try:
        return get_obj_from_relay_id(info, relay_id)
    except ObjectDoesNotExist:
        return None


class ImpersonationStart(RelayMutation):
    """
    Start acting as another user. Returns the session's tokens; the client swaps them in for
    its own and keeps its own to restore on `impersonationEnd`.
    """

    access = graphene.String(description=_("Access token of the session."))
    refresh = graphene.String(description=_("Refresh token of the session."))
    session = graphene.Field(get_object_type_for_model(ImpersonationSession))

    class Input:
        target_user = graphene.ID(required=True, description=_("The user to act as."))
        reason = graphene.String(required=True, description=_("Why the session is needed."))

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input) -> "ImpersonationStart":
        request = info.context
        if get_impersonation(request) is not None:
            raise GraphQLError(
                str(_("End the current impersonation session first.")),
                extensions={"code": "impersonation_active"},
            )

        target = _get_object(info, input["target_user"])
        if not isinstance(target, User):
            raise GraphQLError(str(_("User not found.")), extensions={"code": "not_found"})

        try:
            session, refresh = start_impersonation(
                request.user, target, input["reason"], request=request
            )
        except ValidationError as exc:
            # exc.messages are already translated by start_impersonation.
            # ast-grep-ignore: django-translation-validation-error-literal
            raise GraphQLError(" ".join(exc.messages), extensions={"code": "invalid_input"})
        except ImpersonationNotAllowed:
            raise GraphQLError(
                str(_("You don't have permission to act as this user.")),
                extensions={"code": "permission_required"},
            )

        return cls(access=str(refresh.access_token), refresh=str(refresh), session=session)


class ImpersonationEnd(RelayMutation):
    """
    End an impersonation session: the current request's, or — from the impersonator's own
    account — the one given by `session`.
    """

    session = graphene.Field(get_object_type_for_model(ImpersonationSession))

    class Input:
        session = graphene.ID(
            description=_("The session to end. Defaults to the current request's session.")
        )

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input) -> "ImpersonationEnd":
        request = info.context
        session = get_impersonation(request)

        if session is None:
            session_id = input.get("session")
            session = _get_object(info, session_id) if session_id else None
            if not isinstance(session, ImpersonationSession):
                raise GraphQLError(
                    str(_("There is no impersonation session to end.")),
                    extensions={"code": "not_found"},
                )
            user = request.user
            if session.impersonator_id != user.pk and not user.has_perm(
                f"{ImpersonationSession._meta.app_label}.change_impersonationsession"
            ):
                raise GraphQLError(
                    str(_("You don't have permission to end this session.")),
                    extensions={"code": "permission_required"},
                )
            reason = (
                ImpersonationSession.EndReason.ENDED
                if session.impersonator_id == user.pk
                else ImpersonationSession.EndReason.REVOKED
            )
        else:
            reason = ImpersonationSession.EndReason.ENDED

        end_impersonation(session, reason, request=request)
        return cls(session=session)


class ImpersonationMutations:
    impersonation_start = ImpersonationStart.Field()
    impersonation_end = ImpersonationEnd.Field()
