from collections.abc import Callable, Generator

import pytest
from django.contrib.auth.models import AbstractBaseUser
from django.core.cache import cache

from baseapp_auth.tests.factories import UserFactory

from ..models import ImpersonationSession
from ..services import start_impersonation


@pytest.fixture(autouse=True)
def clear_impersonation_cache() -> Generator[None, None, None]:
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def superuser() -> AbstractBaseUser:
    return UserFactory(is_superuser=True)


@pytest.fixture
def member() -> AbstractBaseUser:
    return UserFactory()


def bearer(token) -> dict[str, str]:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.fixture
def start_session(superuser, member) -> Callable[..., tuple[ImpersonationSession, dict]]:
    """Start a session of `superuser` as `member`; returns the session and its tokens."""

    def start(
        impersonator=None, target=None, reason="Support ticket 42"
    ) -> tuple[ImpersonationSession, dict]:
        session, refresh = start_impersonation(impersonator or superuser, target or member, reason)
        return session, {"access": str(refresh.access_token), "refresh": str(refresh)}

    return start
