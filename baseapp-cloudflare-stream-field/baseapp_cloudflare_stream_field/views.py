import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt

import requests


def direct_creator_upload(request):
    url = f"https://api.cloudflare.com/client/v4/accounts/{settings.CLOUDFLARE_ACCOUNT_ID}/stream?direct_user=true"
    headers = {
        "Authorization": f"Bearer {settings.CLOUDFLARE_API_TOKEN}",
        "Tus-Resumable": request.META.get("HTTP_TUS_RESUMABLE", "1.0.0"),
        "Upload-Length": request.META.get("HTTP_UPLOAD_LENGTH"),
        "Upload-Metadata": request.META.get("HTTP_UPLOAD_METADATA"),
        "Upload-Creator": str(request.user.pk)
        if request.user.is_authenticated
        else None,
    }
    response = requests.post(url, headers=headers)
    if response.status_code == 201:
        return HttpResponseRedirect(
            response.headers["Location"],
            status=201,
            headers={
                "Access-Control-Expose-Headers": "Location, Stream-Media-ID",
                "Stream-Media-ID": response.headers["stream-media-id"],
            },
        )
    else:
        logging.info(response.text)
    return HttpResponse(status=400)


@login_required
@csrf_exempt
def cloudflare_stream_upload(request):
    return direct_creator_upload(request)
