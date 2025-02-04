import os
import uuid
from unittest import mock

import pytest

from baseapp_core.models import random_dir_in, random_name_in

pytestmark = pytest.mark.django_db


@pytest.fixture
def base_dir():
    return "/test/base/dir"


@pytest.fixture
def filename():
    return "testfile.txt"


def test_random_name_in():
    directory = "test_dir"
    filename = "example.txt"
    random_name = random_name_in(directory)

    result = random_name(mock.Mock(), filename)

    # Check if the result is in the correct directory
    assert result.startswith(directory)

    # Check if the result has the correct file extension
    assert result.endswith(".txt")

    # Check if the filename is a valid UUID
    generated_filename = os.path.basename(result)
    generated_uuid = generated_filename.split(".")[0]
    try:
        uuid.UUID(generated_uuid, version=4)
    except ValueError:
        pytest.fail(f"Generated filename '{generated_filename}' is not a valid UUID")


def test_random_dir_in_initialization(base_dir):
    random_dir = random_dir_in(base_dir)
    assert random_dir.base_dir == base_dir


def test_random_dir_in_call(base_dir, filename):
    random_dir = random_dir_in(base_dir)
    instance = mock.Mock()

    with mock.patch("uuid.uuid4", return_value=uuid.UUID("12345678123456781234567812345678")):
        result = random_dir(instance, filename)
        expected_path = os.path.join(base_dir, "12345678-1234-5678-1234-567812345678", filename)
        assert result == expected_path
