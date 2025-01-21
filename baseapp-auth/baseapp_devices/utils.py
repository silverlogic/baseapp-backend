import sys
from hashlib import md5, sha256

from django.conf import settings
from django.core.cache import DEFAULT_CACHE_ALIAS, caches

import requests
from ipware import get_client_ip
from user_agents import parse

# Small snippet from the `six` library to help with Python 3 compatibility
if sys.version_info[0] == 3:
    text_type = str
else:
    text_type = unicode  # noqa


USER_AGENTS_CACHE = getattr(settings, "USER_AGENTS_CACHE", DEFAULT_CACHE_ALIAS)


def get_cache(backend, **kwargs):
    return caches[backend]


if USER_AGENTS_CACHE:
    cache = get_cache(USER_AGENTS_CACHE)
else:
    cache = None


def get_cache_key(ua_string):
    # Some user agent strings are longer than 250 characters so we use its MD5
    if isinstance(ua_string, text_type):
        ua_string = ua_string.encode("utf-8")
    return "".join(["django_user_agents.", md5(ua_string).hexdigest()])


def get_user_agent(request):
    # Tries to get UserAgent objects from cache before constructing a UserAgent
    # from scratch because parsing regexes.yaml/json (ua-parser) is slow
    if not hasattr(request, "META"):
        return ""

    ua_string = request.META.get("HTTP_USER_AGENT", "")

    if not isinstance(ua_string, text_type):
        ua_string = ua_string.decode("utf-8", "ignore")

    if cache:
        key = get_cache_key(ua_string)
        user_agent = cache.get(key)
        if user_agent is None:
            user_agent = parse(ua_string)
            cache.set(key, user_agent)
    else:
        user_agent = parse(ua_string)
    return user_agent


def get_and_set_user_agent(request):
    # If request already has ``user_agent``, it will return that, otherwise
    # call get_user_agent and attach it to request so it can be reused
    if hasattr(request, "user_agent"):
        return request.user_agent

    if not request:
        return parse("")

    request.user_agent = get_user_agent(request)
    return request.user_agent


def get_geo_info(ip):
    try:
        res = requests.get(f"http://ip-api.com/json/{ip}")
        return res.json()
    except Exception as e:
        return {"message": str(e), "status": "error"}


def get_cloudflare_info():
    response = requests.get("https://cloudflare.com/cdn-cgi/trace")
    data_str = response.content.decode("utf-8")
    data_dict = {}
    for line in data_str.splitlines():
        key, value = line.split("=", 1)
        data_dict[key] = value
    return data_dict


def get_ip_address(request):
    ip, _ = get_client_ip(request)
    if not ip:
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")
    return ip


def get_user_ip_geolocation(request):
    ip = get_ip_address(request)
    get_geo_method = getattr(settings, "BASEAPP_DEVICES_GET_GEO_METHOD", get_geo_info)

    if cache:
        key = get_cache_key(ip)
        ip_geolocation = cache.get(key)
        if ip_geolocation is None:
            ip_geolocation = get_geo_method(ip)
            if ip_geolocation["status"] == "fail":
                data = get_cloudflare_info()
                ip = data.get("ip", ip)
                ip_geolocation = get_geo_method(ip)
                key = get_cache_key(ip)
            cache.set(key, ip_geolocation)
    else:
        ip_geolocation = get_geo_method(ip)
        if ip_geolocation["status"] == "fail":
            data = get_cloudflare_info()
            ip_geolocation = get_geo_method(data.get("ip", ip))
    return ip_geolocation


def get_device_id(user_agent, ip_geolocation):
    input_string = f"{user_agent.device.family}-{user_agent.os.family}-{user_agent.browser.family}-{ip_geolocation.get('countryCode', 'unknown')}-{ip_geolocation.get('region', 'unknown')}-{ip_geolocation.get('city', 'unknown')}-{ip_geolocation.get('query', 'unknown')}"
    encoded_string = input_string.encode()
    hash_object = sha256(encoded_string)

    return hash_object.hexdigest()
