from django.urls import path

from cloudflare_stream_field.views import direct_creator_uploads

urlpatterns = [path("", direct_creator_uploads)]
