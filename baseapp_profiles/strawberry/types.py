from typing import Any

import strawberry
import swapper
from django.db.models import Model
from strawberry.types import Info

from baseapp_core.plugins import strawberry_shared_interfaces
from baseapp_core.strawberry import Node, django_type

Profile = swapper.load_model("baseapp_profiles", "Profile")
profile_app_label = Profile._meta.app_label


# Columns read by the permission backends; deferred columns would be refetched per access.
@django_type(Profile, only=["status", "owner_id"])
class ProfileType(*strawberry_shared_interfaces.get("BlocksInterface"), Node):
    """POC slice of the Profile type: enough to host the shared BlocksInterface."""

    name: strawberry.auto

    @classmethod
    def get_node(cls, info: Info, pk: Any) -> Model | None:
        node = super().get_node(info, pk)
        if not info.context.user.has_perm(f"{profile_app_label}.view_profile", node):
            return None
        return node
