from urllib.parse import urlparse

from django.http import HttpRequest, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from baseapp_url_shortening.models import ShortUrl


@csrf_exempt  # NOSONAR - public GET redirect, no state mutation, CSRF not applicable
@require_GET
def redirect_full_url(
    request: HttpRequest, short_code: str = ""
) -> HttpResponseRedirect:  # NOSONAR
    """Resolve short_code to a ShortUrl and redirect to its full_url.

    Args:
        request: The incoming HTTP request.
        short_code: The short code identifying the target URL.

    Returns:
        An HttpResponseRedirect to the associated full URL.

    Raises:
        Http404: If no ShortUrl with the given short_code exists.
        HttpResponseBadRequest: If the stored URL has a non-http/https scheme.
    """
    short_url_object = get_object_or_404(ShortUrl, short_code=short_code)
    if urlparse(short_url_object.full_url).scheme not in {"http", "https"}:
        return HttpResponseBadRequest("Invalid redirect target.")
    return redirect(short_url_object.full_url)
