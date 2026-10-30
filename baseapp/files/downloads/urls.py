"""
The protected download endpoints, mounted on their own so projects that leave the upload
API unmounted can still serve protected files:

    re_path(r"^files/protected/", include("baseapp.files.downloads.urls"))

Mount it where ``BASEAPP_FILES_PROTECTED_DOWNLOADS_URL`` points (default
``/v1/files/protected/``); the files plugin's ``v1_urlpatterns`` already do.
"""

from django.urls import re_path

from .views import ProtectedFileDownloadView, ProtectedFileTicketView

urlpatterns = [
    re_path(
        r"^t/(?P<ticket>[^/]+)$",
        ProtectedFileTicketView.as_view(),
        name="protected-file-ticket",
    ),
    re_path(
        r"^(?P<key>[\w.-]+)/(?P<object_id>[^/]+)$",
        ProtectedFileDownloadView.as_view(),
        name="protected-file-download",
    ),
]
