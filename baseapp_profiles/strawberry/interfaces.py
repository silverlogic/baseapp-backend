from collections.abc import Iterable

import strawberry
import swapper
from django.db.models import Model, Q
from strawberry.types import Info

from baseapp_core.strawberry import CountedConnection, Node, type_for_model
from baseapp_core.strawberry.connections import connection

from ..filters import ProfileFilter

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileLazyType = type_for_model(Profile)


@strawberry.interface(name="ProfileInterface")
class ProfileInterface(Node):
    profile: ProfileLazyType | None


@strawberry.interface(name="ProfilesInterface")
class ProfilesInterface(Node):
    @connection(CountedConnection[ProfileLazyType] | None, filterset_class=ProfileFilter)
    def profiles(self, info: Info) -> Iterable[Model]:
        user = info.context.user
        if user.is_authenticated and user == self:
            # distinct(): the OR spans the to-many `members` relation.
            return (
                Profile.objects.filter(Q(owner_id=user.id) | Q(members__user_id=user.id))
                .distinct()
                .order_by("name")
            )
        return Profile.objects.none()


def get_profile_interface() -> type[ProfileInterface]:
    return ProfileInterface


def get_profiles_interface() -> type[ProfilesInterface]:
    return ProfilesInterface
