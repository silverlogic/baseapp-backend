import pytest
from rest_framework_simplejwt.tokens import AccessToken

from ...services import SESSION_CLAIM, has_session_claim


def _token(**claims: object) -> str:
    token = AccessToken()
    for name, value in claims.items():
        token[name] = value
    return str(token)


def test_session_token_has_the_claim() -> None:
    assert has_session_claim(_token(**{SESSION_CLAIM: 1})) is True


def test_ordinary_token_has_no_claim() -> None:
    assert has_session_claim(_token(user_id=1)) is False


def test_bytes_are_accepted() -> None:
    assert has_session_claim(_token(**{SESSION_CLAIM: 1}).encode()) is True


@pytest.mark.parametrize("raw", ["", "not-a-jwt", "a.b.c"])
def test_malformed_token_has_no_claim(raw: str) -> None:
    assert has_session_claim(raw) is False


def test_claim_is_read_without_checking_the_signature() -> None:
    # A forged session token passes the pre-check; the full validation that follows
    # (signature, then session) is what rejects it.
    header, payload, _signature = _token(**{SESSION_CLAIM: 1}).split(".")
    assert has_session_claim(f"{header}.{payload}.forged") is True
