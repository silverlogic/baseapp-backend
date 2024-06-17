
from django.utils.deprecation import MiddlewareMixin as BaseMiddleware
from baseapp_core.graphql import get_pk_from_relay_id
import swapper
Profile = swapper.load_model("baseapp_profiles", "Profile")


class CurrentProfileMiddleware(BaseMiddleware):
    def process_request(self, request):
        current_profile_header = request.headers.get('Current-Profile')
        if current_profile_header:
            try:
                pk = get_pk_from_relay_id(current_profile_header)
                request.user.current_profile = Profile.objects.get(pk=pk)
            except Profile.DoesNotExist:
                request.user.current_profile = request.user.profile
        else:
            request.user.current_profile = request.user.profile
