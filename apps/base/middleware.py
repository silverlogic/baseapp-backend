from django.conf import settings
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin

import pytz


class AdminTimezoneMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # Accessing request.user will activate the sessions/auth middleware.  This
        # causes the Vary: Cookie header to be set.  If this happens on an API call
        # it will greatly reduce the effectiveness of http caching (e.g. using varnish).
        # To get around this we make sure we only access the request user if we the URL matches
        # the admin.
        if request.path.startswith("/admin") and request.user.is_superuser:
            timezone.activate(pytz.timezone(settings.ADMIN_TIME_ZONE))
