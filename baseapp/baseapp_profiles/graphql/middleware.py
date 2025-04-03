import logging

import swapper

from baseapp_core.graphql import get_pk_from_relay_id

Profile = swapper.load_model("baseapp_profiles", "Profile")
profile_app_label = Profile._meta.app_label


class CurrentProfileMiddleware(object):
    def on_error(self, error):
        # need to raise error again to get access to traceback
        try:
            raise error
        except Exception as error:
            logging.exception(error)
            raise error

    def resolve(self, next, root, info, **args):
        current_profile_header = info.context.headers.get("Current-Profile")

        if not info.context.user.is_authenticated:
            info.context.user.current_profile = None

        if not hasattr(info.context.user, "current_profile"):
            if not current_profile_header:
                info.context.user.current_profile = info.context.user.profile
            else:
                info.context.user.current_profile = None
                pk = get_pk_from_relay_id(current_profile_header)
                if pk:
                    profile = Profile.objects.filter(pk=pk).first()
                    if profile and info.context.user.has_perm(
                        f"{profile_app_label}.use_profile", profile
                    ):
                        info.context.user.current_profile = profile

        return next(root, info, **args)
