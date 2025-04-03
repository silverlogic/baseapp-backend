import swapper
from django.utils.deprecation import MiddlewareMixin as BaseMiddleware

from baseapp_core.graphql import get_pk_from_relay_id

Profile = swapper.load_model("baseapp_profiles", "Profile")
profile_app_label = Profile._meta.app_label


class CurrentProfileMiddleware(BaseMiddleware):
    def process_request(self, request):
        current_profile_header = request.headers.get("Current-Profile")
        request.user.current_profile = None

        if not request.user.is_authenticated:
            return

        if not current_profile_header:
            request.user.current_profile = request.user.profile
        else:
            pk = get_pk_from_relay_id(current_profile_header)
            if pk:
                profile = Profile.objects.filter(pk=pk).first()

                if profile and request.user.has_perm(f"{profile_app_label}.use_profile", profile):
                    request.user.current_profile = profile
