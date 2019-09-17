import os
import re

import pytest


def pytest_runtest_setup(item):
    pytest.api_version = re.search(r"v\d+", os.path.realpath(__file__)).group(0)
