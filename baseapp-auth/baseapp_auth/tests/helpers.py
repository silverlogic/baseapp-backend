import json

from baseapp_core.tests.helpers import *  # noqa: F403, F401


def get_json(data):
    return json.loads(json.dumps(data))
