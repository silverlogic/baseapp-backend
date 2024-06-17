
from django.utils.deprecation import MiddlewareMixin as BaseMiddleware
from baseapp_core.graphql import get_pk_from_relay_id
import swapper
Profile = swapper.load_model("baseapp_profiles", "Profile")


class CurrentProfileMiddleware(BaseMiddleware):
    def process_request(self, request):
        current_profile_header = request.headers.get('Current-Profile')

        if not request.user.is_authenticated:
            return

        if current_profile_header:
            pk = get_pk_from_relay_id(current_profile_header)
            profile = Profile.objects.first(pk=pk)

            if profile and request.user.has_perm("baseapp_profiles.use_profile", profile):
                request.user.current_profile = profile
            else:
                request.user.current_profile = request.user.profile
