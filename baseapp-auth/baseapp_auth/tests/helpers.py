import json

from baseapp_core.tests.helpers import *


def get_json(data):
    return json.loads(json.dumps(data))
