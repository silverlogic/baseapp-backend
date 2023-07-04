import os
import re

import pytest


def pytest_runtest_setup(item):
    pytest.api_version = re.findall(r"v\d+", os.path.realpath(__file__))[-1]
