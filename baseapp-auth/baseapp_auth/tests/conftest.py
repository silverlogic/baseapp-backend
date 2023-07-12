import sys
from os.path import abspath, dirname as d, join

# add the test root dir to python path
root_dir = d(d(abspath(__file__)))
sys.path.append(root_dir)

from baseapp_core.tests.fixtures import *  # noqa

from .fixtures import *  # noqa
from .fixtures_mfa import *  # noqa
