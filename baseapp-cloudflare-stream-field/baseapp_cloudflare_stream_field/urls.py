from baseapp_cloudflare_stream_field.views import cloudflare_stream_upload
from django.urls import path

urlpatterns = [path("", cloudflare_stream_upload)]
