from django.urls import path

from baseapp_cloudflare_stream_field.views import cloudflare_stream_upload

urlpatterns = [path("", cloudflare_stream_upload)]
