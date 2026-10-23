from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.exceptions import APIException


class Gone(APIException):
    """
    The file existed but is no longer available (e.g. a revoked document). Raise it from a
    spec's ``check`` to answer ``410 Gone``; GraphQL reports it with the code ``gone``.
    """

    status_code = status.HTTP_410_GONE
    default_detail = _("This file is no longer available.")
    default_code = "gone"
