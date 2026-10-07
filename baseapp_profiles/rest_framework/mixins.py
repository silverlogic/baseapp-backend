import swapper

from baseapp_core.graphql import get_pk_from_relay_id

Profile = swapper.load_model("baseapp_profiles", "Profile")
profile_app_label = Profile._meta.app_label


class CurrentProfileMixin:
    """
    Mixin to set current_profile on request.user for REST framework views.

    This replicates the logic from baseapp_profiles.middleware.CurrentProfileMiddleware
    and baseapp_profiles.graphql.middleware.CurrentProfileMiddleware for DRF views.

    Usage:
        class MyViewSet(CurrentProfileMixin, viewsets.ModelViewSet):
            ...
    """

    def initial(self, request, *args, **kwargs):
        """
        Runs anything that needs to occur prior to calling the method handler.
        This is where we set the current_profile.
        """
        super().initial(request, *args, **kwargs)
        self.set_current_profile(request)

    def set_current_profile(self, request):
        """
        Set current_profile on request.user based on Current-Profile header.
        """
        current_profile_header = request.headers.get("Current-Profile")
        request.user.current_profile = None

        if not request.user.is_authenticated:
            return

        if not current_profile_header:
            # No header provided, use the user's default profile
            request.user.current_profile = request.user.profile
        else:
            # Header provided, try to load the specified profile
            pk = get_pk_from_relay_id(current_profile_header)
            if pk:
                profile = Profile.objects.filter(pk=pk).first()

                # Check if user has permission to use this profile
                if profile and request.user.has_perm(f"{profile_app_label}.use_profile", profile):
                    request.user.current_profile = profile
