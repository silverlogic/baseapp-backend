from unittest import mock

import pytest
from constance import config
from django.core.exceptions import ValidationError

from ..validators import blocked_words_validator

pytestmark = pytest.mark.django_db

SAMPLE_BLOCKED_WORDS = "badword1, badword2, badword3"


@pytest.fixture
def mock_config_blocklisted_words():
    with mock.patch("baseapp_comments.validators.config", spec=config) as mock_config:
        mock_config.BLOCKLISTED_WORDS = SAMPLE_BLOCKED_WORDS
        yield


def test_blocked_words_validator_no_errors(mock_config_blocklisted_words):
    # Test case with no blocked words
    text = "This is a clean text without any inappropriate words."
    assert blocked_words_validator(text) is None


def test_blocked_words_validator_with_errors(mock_config_blocklisted_words):
    # Test case with a blocked word
    text = "This text contains a blocked word: badword1."
    with pytest.raises(ValidationError):
        blocked_words_validator(text)


def test_blocked_words_validator_with_errors_case_insensitive(mock_config_blocklisted_words):
    # Test case with a blocked word in a different case
    text = "This text contains a blocked word in uppercase: BADWORD2."
    with pytest.raises(ValidationError):
        blocked_words_validator(text)
