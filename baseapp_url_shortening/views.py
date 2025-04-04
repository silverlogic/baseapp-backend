from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt

from baseapp_url_shortening.models import ShortUrl


@csrf_exempt
def redirect_full_url(request, short_code=""):
    short_url_object = get_object_or_404(ShortUrl, short_code=short_code)
    return redirect(short_url_object.full_url)
