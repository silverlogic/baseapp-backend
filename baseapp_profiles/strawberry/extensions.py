from collections.abc import Generator

import swapper
from strawberry.extensions import SchemaExtension

from baseapp_core.graphql import get_pk_from_relay_id

Profile = swapper.load_model("baseapp_profiles", "Profile")
profile_app_label = Profile._meta.app_label


class CurrentProfileExtension(SchemaExtension):
    """Once per operation, set `user.current_profile` from the `Current-Profile` header."""

    def on_execute(self) -> Generator[None, None, None]:
        request = self.execution_context.context
        user = request.user
        if not user.is_authenticated:
            user.current_profile = None
        if not hasattr(user, "current_profile"):
            header = request.headers.get("Current-Profile")
            user.current_profile = None if header else user.profile
            if header and (pk := get_pk_from_relay_id(header)):
                profile = Profile.objects.filter(pk=pk).first()
                if profile and user.has_perm(f"{profile_app_label}.use_profile", profile):
                    user.current_profile = profile
        yield
