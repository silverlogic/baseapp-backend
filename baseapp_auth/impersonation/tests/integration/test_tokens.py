from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework_simplejwt.utils import datetime_to_epoch

from ...models import ImpersonationSession
from ...services import end_impersonation, get_session
from ...signals import impersonation_ended
from ..fixtures import bearer

pytestmark = pytest.mark.django_db

REFRESH_URL = "/v1/auth/jwt/refresh"


def add_mfa_claim(refresh, target, impersonator) -> None:
    refresh["mfa"] = f"{target.pk}:{impersonator.pk}"


@override_settings(
    BASEAPP_AUTH_IMPERSONATION_TOKEN_HOOK=(
        "baseapp_auth.impersonation.tests.integration.test_tokens.add_mfa_claim"
    )
)
def test_token_hook_adds_claims(superuser, member, start_session) -> None:
    _session, tokens = start_session()
    expected = f"{member.pk}:{superuser.pk}"
    assert RefreshToken(tokens["refresh"])["mfa"] == expected
    assert AccessToken(tokens["access"])["mfa"] == expected


def test_refresh_keeps_the_session_and_its_expiry(client, start_session) -> None:
    session, tokens = start_session()
    response = client.post(REFRESH_URL, {"refresh": tokens["refresh"]})
    assert response.status_code == 200
    access = AccessToken(response.json()["access"])
    assert access["imp_sid"] == session.pk
    assert access["exp"] <= datetime_to_epoch(session.expires_at)


@override_settings(BASEAPP_AUTH_IMPERSONATION_TTL=60)
def test_access_token_never_outlives_a_short_session(client, start_session) -> None:
    session, tokens = start_session()
    assert AccessToken(tokens["access"])["exp"] == datetime_to_epoch(session.expires_at)
    response = client.post(REFRESH_URL, {"refresh": tokens["refresh"]})
    assert AccessToken(response.json()["access"])["exp"] == datetime_to_epoch(session.expires_at)


def test_refresh_after_end_is_refused(client, start_session) -> None:
    session, tokens = start_session()
    end_impersonation(session)
    response = client.post(REFRESH_URL, {"refresh": tokens["refresh"]})
    assert response.status_code == 401
    assert response.json()["code"] == "impersonation_ended"


def test_ordinary_refresh_still_works(client, member) -> None:
    response = client.post(REFRESH_URL, {"refresh": str(RefreshToken.for_user(member))})
    assert response.status_code == 200


def test_expired_session_is_refused_and_closed(client, start_session) -> None:
    session, tokens = start_session()
    received = []
    impersonation_ended.connect(lambda **kw: received.append(kw), weak=False, dispatch_uid="exp")
    ImpersonationSession.objects.filter(pk=session.pk).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    try:
        response = client.get("/v1/users/me", **bearer(tokens["access"]))
    finally:
        impersonation_ended.disconnect(dispatch_uid="exp")

    # The cached copy still says the session runs; its expiry is checked on every request.
    assert response.status_code == 401
    session.refresh_from_db()
    assert session.end_reason == ImpersonationSession.EndReason.EXPIRED
    assert received[0]["request"] is None


def test_session_is_revoked_when_impersonator_is_deactivated(
    client, superuser, start_session
) -> None:
    session, tokens = start_session()
    superuser.is_active = False
    superuser.save()
    response = client.get("/v1/users/me", **bearer(tokens["access"]))
    assert response.status_code == 401
    session.refresh_from_db()
    assert session.end_reason == ImpersonationSession.EndReason.REVOKED


def test_token_must_match_its_session(client, member, start_session) -> None:
    session, tokens = start_session()
    forged = AccessToken(tokens["access"])
    forged["imp"] = member.pk
    response = client.get("/v1/users/me", **bearer(str(forged)))
    assert response.status_code == 401


def test_unknown_session_is_refused(client, start_session) -> None:
    session, tokens = start_session()
    ImpersonationSession.objects.filter(pk=session.pk).delete()
    response = client.get("/v1/users/me", **bearer(tokens["access"]))
    assert response.status_code == 401


def test_end_is_idempotent_and_clears_the_cache(start_session) -> None:
    session, _tokens = start_session()
    assert get_session(session.pk).ended_at is None
    assert end_impersonation(session) is True
    assert end_impersonation(session) is False
    assert get_session(session.pk).ended_at is not None


def test_ending_an_expired_session_records_expiry(start_session) -> None:
    session, _tokens = start_session()
    session.expires_at = timezone.now() - timedelta(minutes=1)
    end_impersonation(session)
    session.refresh_from_db()
    assert session.end_reason == ImpersonationSession.EndReason.EXPIRED


def test_bad_tokens_are_left_to_authentication(client) -> None:
    response = client.get("/v1/users/me", **bearer("not-a-token"))
    assert response.status_code == 401
    assert "code" not in response.json() or response.json()["code"] != "impersonation_ended"
