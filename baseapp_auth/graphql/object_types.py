import graphene
from django.apps import apps
from django.contrib.auth import get_user_model
from graphene import relay
from query_optimizer import optimize

from baseapp_core.graphql import DjangoObjectType, ThumbnailField

from .filters import UsersFilter
from .permissions import PermissionsInterface

User = get_user_model()

interfaces = (relay.Node, PermissionsInterface)
inheritances = tuple()

if apps.is_installed("baseapp_notifications"):
    from baseapp_notifications.graphql.object_types import NotificationsInterface

    interfaces += (NotificationsInterface,)


if apps.is_installed("baseapp_pages"):
    from baseapp_pages.graphql.object_types import MetadataObjectType, PageInterface

    interfaces += (PageInterface,)


if apps.is_installed("baseapp_ratings"):
    from baseapp_ratings.graphql.object_types import RatingsInterface

    interfaces += (RatingsInterface,)


if apps.is_installed("baseapp_profiles"):
    from baseapp_profiles.graphql.object_types import (
        ProfileInterface,
        ProfilesInterface,
    )

    interfaces += (ProfilesInterface, ProfileInterface)


if apps.is_installed("baseapp.activity_log"):
    from baseapp.activity_log.graphql.interfaces import UserActivityLog

    inheritances += (UserActivityLog,)


class AbstractUserObjectType(*inheritances, object):
    is_authenticated = graphene.Boolean()
    full_name = graphene.String()

    first_name = graphene.String(deprecation_reason="Deprecated in favor of fullName and shortName")
    last_name = graphene.String(deprecation_reason="Deprecated in favor of fullName and shortName")

    avatar = ThumbnailField(required=False)

    # Make them not required
    email = graphene.String()
    phone_number = graphene.String()
    is_superuser = graphene.Boolean()
    is_staff = graphene.Boolean()
    is_email_verified = graphene.Boolean()
    password_changed_date = graphene.DateTime()
    new_email = graphene.String()
    is_new_email_confirmed = graphene.Boolean()

    class Meta:
        model = User
        fields = (
            "pk",
            "first_name",
            "last_name",
            "full_name",
            "email",
            "phone_number",
            "is_superuser",
            "is_staff",
            "is_active",
            "is_email_verified",
            "date_joined",
            "password_changed_date",
            "new_email",
            "is_new_email_confirmed",
            "is_authenticated",
            "pages",
            "comments",
            "reactions",
            "last_login",
            "profiles",
        )
        interfaces = interfaces
        filterset_class = UsersFilter

    def resolve_avatar(self, *args, **kwargs):
        return self.profile.image

    def resolve_metadata(self, *args, **kwargs):
        return MetadataObjectType(
            meta_title=self.get_full_name(),
        )

    def resolve_is_authenticated(self, info):
        return info.context.user.is_authenticated and self.pk == info.context.user.pk

    def resolve_full_name(self, *args, **kwargs):
        return self.profile.name

    def resolve_email(self, info):
        return view_user_private_field(self, info, "email")

    def resolve_phone_number(self, info):
        return view_user_private_field(self, info, "phone_number")

    def resolve_is_superuser(self, info):
        return view_user_private_field(self, info, "is_superuser")

    def resolve_is_staff(self, info):
        return view_user_private_field(self, info, "is_staff")

    def resolve_is_email_verified(self, info):
        return view_user_private_field(self, info, "is_email_verified")

    def resolve_password_changed_date(self, info):
        return view_user_private_field(self, info, "password_changed_date")

    def resolve_new_email(self, info):
        return view_user_private_field(self, info, "new_email")

    def resolve_is_new_email_confirmed(self, info):
        return view_user_private_field(self, info, "is_new_email_confirmed")

    MAX_COMPLEXITY = 3

    @classmethod
    def get_queryset(cls, queryset, info):
        if info.context.user.is_anonymous:
            return optimize(
                queryset.filter(is_active=True), info, max_complexity=cls.MAX_COMPLEXITY
            )
        return optimize(queryset, info, max_complexity=cls.MAX_COMPLEXITY)

    @classmethod
    def get_node(self, info, id):
        node = super().get_node(info, id)
        if not info.context.user.has_perm(f"{User._meta.app_label}.view_user", node):
            return None
        return node


class UserObjectType(AbstractUserObjectType, DjangoObjectType):
    class Meta(AbstractUserObjectType.Meta):
        pass


def view_user_private_field(user, info, field_name):
    if info.context.user.has_perm(f"{User._meta.app_label}.view_user_{field_name}", user):
        return getattr(user, field_name)
