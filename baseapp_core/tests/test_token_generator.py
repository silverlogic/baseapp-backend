import pytest
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from baseapp_core.tokens import TokenGenerator


class TestTokenGenerator(TokenGenerator):
    @property
    def key_salt(self) -> str:
        return "test_salt"

    @property
    def max_age(self) -> int:
        return 3600


class MockObject:
    def __init__(self, id) -> None:
        self.id = id


@pytest.fixture
def token_generator() -> TestTokenGenerator:
    return TestTokenGenerator()


@pytest.fixture
def mock_object() -> MockObject:
    return MockObject(id=123)


def test_make_token(token_generator, mock_object) -> None:
    token = token_generator.make_token(mock_object)
    assert token is not None
    assert isinstance(token, str)


def test_get_signing_value(token_generator, mock_object) -> None:
    value = token_generator.get_signing_value(mock_object)
    assert value == mock_object.id


def test_check_token_valid(token_generator, mock_object) -> None:
    token = token_generator.make_token(mock_object)
    assert token_generator.check_token(mock_object, token) is True


def test_check_token_invalid(token_generator, mock_object) -> None:
    invalid_token = urlsafe_base64_encode(force_bytes("invalid_token"))
    assert token_generator.check_token(mock_object, invalid_token) is False


def test_is_value_valid(token_generator, mock_object) -> None:
    value = token_generator.get_signing_value(mock_object)
    assert token_generator.is_value_valid(mock_object, value) is True


def test_decode_token_valid(token_generator, mock_object) -> None:
    token = token_generator.make_token(mock_object)
    decoded_value = token_generator.decode_token(token)
    assert decoded_value == mock_object.id


def test_decode_token_invalid(token_generator) -> None:
    invalid_token = urlsafe_base64_encode(force_bytes("invalid_token"))
    assert token_generator.decode_token(invalid_token) is None


def test_key_salt_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        TokenGenerator().key_salt
