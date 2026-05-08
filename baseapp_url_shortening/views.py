from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from baseapp_url_shortening.models import ShortUrl


@csrf_exempt  # NOSONAR - public GET redirect, no state mutation, CSRF not applicable
@require_GET
def redirect_full_url(
    request: HttpRequest, short_code: str = ""
) -> HttpResponseRedirect:  # NOSONAR
    short_url_object = get_object_or_404(ShortUrl, short_code=short_code)
    return redirect(short_url_object.full_url)
