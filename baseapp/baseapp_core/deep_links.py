import requests
from django.conf import settings
from requests.exceptions import RequestException

from .exceptions import DeepLinkFetchError


def get_deep_link(
    fallback_url=None,
    for_ios=False,
    for_android=False,
    for_windows_phone=False,
    for_blackberry=False,
    for_fire=False,
    **kwargs,
):
    """
    Create Branch.io deep link
    Valid params and return value can be found at:
    https://github.com/BranchMetrics/branch-deep-linking-public-api#creating-a-deep-linking-url
    """
    kwargs["branch_key"] = settings.BRANCHIO_KEY

    if fallback_url:
        kwargs["data"]["$desktop_url"] = fallback_url
        if not for_ios:
            kwargs["data"]["$ios_url"] = fallback_url
        if not for_android:
            kwargs["data"]["$android_url"] = fallback_url
        if not for_windows_phone:
            kwargs["data"]["$windows_phone_url"] = fallback_url
        if not for_blackberry:
            kwargs["data"]["$blackberry_url"] = fallback_url
        if not for_fire:
            kwargs["data"]["$fire_url"] = fallback_url
    try:
        r = requests.post("https://api.branch.io/v1/url", json=kwargs)
        r.raise_for_status()
    except RequestException:
        raise DeepLinkFetchError

    results = r.json()
    if "url" not in results:
        raise DeepLinkFetchError
    return results
