from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt

from baseapp_url_shortening.models import ShortUrl


@csrf_exempt  # NOSONAR - public GET redirect, no state mutation, CSRF not applicable
def redirect_full_url(request, short_code=""):  # NOSONAR
    short_url_object = get_object_or_404(ShortUrl, short_code=short_code)
    return redirect(short_url_object.full_url)
