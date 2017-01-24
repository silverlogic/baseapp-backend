from django.conf import settings

import requests
from requests.exceptions import RequestException

from .exceptions import DeepLinkFetchError


def get_deep_link(**kwargs):
    """
    Create Branch.io deep link
    Valid params and return value can be found at:
    https://github.com/BranchMetrics/branch-deep-linking-public-api#creating-a-deep-linking-url
    """
    kwargs['branch_key'] = settings.BRANCH_KEY
    try:
        r = requests.post('https://api.branch.io/v1/url', json=kwargs)
        r.raise_for_status()
    except RequestException:
        raise DeepLinkFetchError
    else:
        return r.json()
