import sys
from os.path import dirname as d
from os.path import abspath, join

# add the test root dir to python path
root_dir = d(d(abspath(__file__)))
sys.path.append(root_dir)

from .fixtures import *  # noqa
from .fixtures_mfa import *  # noqa
