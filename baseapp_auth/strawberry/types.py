from datetime import datetime
from typing import Any

import strawberry
import strawberry_django
from django.contrib.auth import get_user_model
from django.db.models import Model, QuerySet
from strawberry.types import Info

from baseapp_core.plugins import strawberry_shared_interfaces
from baseapp_core.strawberry import Node, django_type
from baseapp_core.strawberry.complexity import check_max_complexity
from baseapp_core.strawberry.fields import thumbnail_field

from .permissions import PermissionsInterface

User = get_user_model()
user_app_label = User._meta.app_label
DEPRECATED_NAME = "Deprecated in favor of fullName and shortName"


def view_user_private_field(user: Model, info: Info, field_name: str) -> Any:
    if info.context.user.has_perm(f"{user_app_label}.view_user_{field_name}", user):
        return getattr(user, field_name)
    return None


def _profile_image(user: Model) -> Any:
    profile = getattr(user, "profile", None)
    return profile.image if profile else None


@strawberry_django.type(User, name="AbstractUser")
class AbstractUserType:
    """User fields, shared by the package type and project overrides (subclass and re-decorate)."""

    last_login: strawberry.auto
    date_joined: strawberry.auto
    is_active: strawberry.auto
    pk: int | None = strawberry_django.field()
    first_name: str | None = strawberry_django.field(deprecation_reason=DEPRECATED_NAME)
    last_name: str | None = strawberry_django.field(deprecation_reason=DEPRECATED_NAME)
    avatar: str | None = thumbnail_field(_profile_image)

    @strawberry_django.field(only=["id"])
    def is_authenticated(self, info: Info) -> bool | None:
        return info.context.user.is_authenticated and self.pk == info.context.user.pk

    @strawberry_django.field(only=["first_name", "last_name"])
    def full_name(self, info: Info) -> str | None:
        if profile := getattr(self, "profile", None):
            return profile.name
        return self.get_full_name()

    @strawberry_django.field(only=["email"])
    def email(self, info: Info) -> str | None:
        return view_user_private_field(self, info, "email")

    @strawberry_django.field(only=["phone_number"])
    def phone_number(self, info: Info) -> str | None:
        return view_user_private_field(self, info, "phone_number")

    @strawberry_django.field(only=["is_superuser"])
    def is_superuser(self, info: Info) -> bool | None:
        return view_user_private_field(self, info, "is_superuser")

    @strawberry_django.field(only=["is_staff"])
    def is_staff(self, info: Info) -> bool | None:
        return view_user_private_field(self, info, "is_staff")

    @strawberry_django.field(only=["is_email_verified"])
    def is_email_verified(self, info: Info) -> bool | None:
        return view_user_private_field(self, info, "is_email_verified")

    @strawberry_django.field(only=["password_changed_date"])
    def password_changed_date(self, info: Info) -> datetime | None:
        return view_user_private_field(self, info, "password_changed_date")

    @strawberry_django.field(only=["new_email"])
    def new_email(self, info: Info) -> str | None:
        return view_user_private_field(self, info, "new_email")

    @strawberry_django.field(only=["is_new_email_confirmed"])
    def is_new_email_confirmed(self, info: Info) -> bool | None:
        return view_user_private_field(self, info, "is_new_email_confirmed")

    MAX_COMPLEXITY = 3

    @classmethod
    def get_queryset(cls, queryset: QuerySet, info: Info, **kwargs: Any) -> QuerySet:
        check_max_complexity(info, cls.MAX_COMPLEXITY)
        if info.context.user.is_anonymous:
            return queryset.filter(is_active=True)
        return queryset

    @classmethod
    def get_node(cls, info: Info, pk: Any) -> Model | None:
        node = super().get_node(info, pk)
        if not info.context.user.has_perm(f"{user_app_label}.view_user", node):
            return None
        return node


def user_interfaces() -> tuple[type, ...]:
    return (
        *strawberry_shared_interfaces.get(
            "RatingsInterface",
            "UserActivityLogInterface",
            "NotificationsInterface",
            "ProfileInterface",
            "ProfilesInterface",
            "PageInterface",
        ),
        PermissionsInterface,
        Node,
    )


@django_type(User, only=["is_active"], relations=("pages", "comments", "reactions"))
class UserType(AbstractUserType, *user_interfaces()):
    pass
