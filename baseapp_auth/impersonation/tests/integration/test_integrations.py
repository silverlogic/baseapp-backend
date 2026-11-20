import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import Permission
from django.test import RequestFactory, override_settings
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from baseapp_auth.tests.factories import UserFactory

from ...authentication import ImpersonationJWTAuthentication
from ...channels import ImpersonationWebsocketMiddleware
from ...exceptions import ImpersonationReadOnly, ImpersonationSessionInvalid
from ...services import (
    _current_session,
    check_impersonation,
    end_impersonation,
    get_impersonation,
    is_impersonated,
)
from ..fixtures import bearer

pytestmark = pytest.mark.django_db


def drf_request(method: str, token: str) -> Request:
    factory = APIRequestFactory()
    request = getattr(factory, method)("/v1/anything", **bearer(token))
    return APIView().initialize_request(request)


class TestJWTAuthentication:
    def test_attaches_the_session(self, member, start_session) -> None:
        session, tokens = start_session()
        request = drf_request("get", tokens["access"])
        user, _token = ImpersonationJWTAuthentication().authenticate(request)
        assert user == member
        assert user.impersonation == session
        assert request._request.impersonation == session
        assert get_impersonation(user) == session

    def test_refuses_writes_in_read_only_sessions(self, start_session) -> None:
        _session, tokens = start_session()
        with pytest.raises(ImpersonationReadOnly):
            ImpersonationJWTAuthentication().authenticate(drf_request("post", tokens["access"]))

    @override_settings(BASEAPP_AUTH_IMPERSONATION_READ_ONLY=False)
    def test_allows_writes_when_acting_as(self, start_session) -> None:
        _session, tokens = start_session()
        user, _token = ImpersonationJWTAuthentication().authenticate(
            drf_request("post", tokens["access"])
        )
        assert user.impersonation is not None

    def test_refuses_ended_sessions(self, start_session) -> None:
        session, tokens = start_session()
        end_impersonation(session)
        with pytest.raises(ImpersonationSessionInvalid):
            ImpersonationJWTAuthentication().authenticate(drf_request("get", tokens["access"]))

    def test_ordinary_tokens_pass(self, member) -> None:
        access = str(RefreshToken.for_user(member).access_token)
        user, _token = ImpersonationJWTAuthentication().authenticate(drf_request("post", access))
        assert user == member
        assert not is_impersonated(user)

    def test_no_header(self) -> None:
        request = APIView().initialize_request(APIRequestFactory().get("/"))
        assert ImpersonationJWTAuthentication().authenticate(request) is None


class TestPermissionsBackend:
    @override_settings(BASEAPP_AUTH_IMPERSONATION_DENIED_PERMISSIONS=["users.view_user"])
    def test_denies_listed_permissions_while_impersonated(self, member, start_session) -> None:
        member.user_permissions.add(
            *Permission.objects.filter(codename="view_user", content_type__app_label="users")
        )
        assert member.has_perm("users.view_user")

        session, _tokens = start_session()
        member = type(member).objects.get(pk=member.pk)
        member.impersonation = session
        assert not member.has_perm("users.view_user")

    @override_settings(BASEAPP_AUTH_IMPERSONATION_DENIED_PERMISSIONS=["users.view_user"])
    def test_finds_the_session_of_the_current_request(self, member, start_session) -> None:
        member.user_permissions.add(
            *Permission.objects.filter(codename="view_user", content_type__app_label="users")
        )
        session, _tokens = start_session()
        context_token = _current_session.set(session)
        try:
            fresh = type(member).objects.get(pk=member.pk)
            assert get_impersonation() == session
            assert not fresh.has_perm("users.view_user")
            # Someone else in the same request is unaffected.
            assert get_impersonation(UserFactory()) is None
        finally:
            _current_session.reset(context_token)


class TestCheckImpersonation:
    def test_scope(self, member, start_session) -> None:
        session, tokens = start_session()
        scope = {"user": member}
        assert check_impersonation(scope, AccessToken(tokens["access"])) == session
        assert scope["impersonation"] == session
        assert member.impersonation == session
        assert get_impersonation(scope) == session

    def test_reuses_an_attached_session(self, start_session) -> None:
        session, tokens = start_session()
        request = RequestFactory().get("/")
        request.impersonation = session
        end_impersonation(session)
        # Already validated earlier in this request, so not looked up again.
        assert check_impersonation(request, AccessToken(tokens["access"])) == session


@pytest.mark.django_db(transaction=True)
class TestWebsocketMiddleware:
    """The middleware reads the database from a worker thread, which only sees committed
    rows."""

    def run(self, scope: dict) -> dict:
        async def inner(scope, receive, send) -> dict:
            return scope

        return async_to_sync(ImpersonationWebsocketMiddleware(inner))(scope, None, None)

    def test_sets_the_session(self, member, start_session) -> None:
        session, tokens = start_session()
        scope = {"subprotocols": ["Authorization", tokens["access"]], "user": member}
        assert self.run(scope)["impersonation"] == session
        assert member.impersonation == session

    def test_refuses_ended_sessions(self, member, start_session) -> None:
        session, tokens = start_session()
        end_impersonation(session)
        scope = {"subprotocols": ["Authorization", tokens["access"]], "user": member}
        with pytest.raises(ValueError):
            self.run(scope)

    def test_ignores_bad_and_missing_tokens(self) -> None:
        assert "impersonation" not in self.run({"subprotocols": ["Authorization", "bad"]})
        assert "impersonation" not in self.run({"subprotocols": []})
