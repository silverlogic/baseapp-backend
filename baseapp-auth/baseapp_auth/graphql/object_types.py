import graphene
import swapper
from baseapp_core.graphql import (
    DjangoObjectType,
    ThumbnailField,
    get_object_type_for_model,
)
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db.models import Q
from graphene import relay

from .filters import UsersFilter
from .permissions import PermissionsInterface

User = get_user_model()

interfaces = (relay.Node, PermissionsInterface)

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
    from baseapp_profiles.graphql.object_types import ProfileInterface

    Profile = swapper.load_model("baseapp_profiles", "Profile")

    class UserProfiles(relay.Node):
        profiles = graphene.List(get_object_type_for_model(Profile))

        def resolve_profiles(self, info):
            if not info.context.user.is_authenticated or self.id != info.context.user.id:
                return Profile.objects.none()
            return Profile.objects.filter(
                Q(owner_id=info.context.user.id) | Q(members__user_id=info.context.user.id)
            )

    interfaces += (UserProfiles, ProfileInterface)


class AbstractUserObjectType(object):
    is_authenticated = graphene.Boolean()
    full_name = graphene.String()
    short_name = graphene.String()

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
            "full_name",
            "short_name",
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

    def resolve_avatar(self, info, width, height):
        return self.profile.image

    def resolve_metadata(self, info):
        return MetadataObjectType(
            meta_title=self.get_full_name(),
        )

    def resolve_is_authenticated(self, info):
        return info.context.user.is_authenticated and self.pk == info.context.user.pk

    def resolve_full_name(self, info):
        return self.profile.name

    def resolve_short_name(self, info):
        return self.get_short_name()

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

    @classmethod
    def get_queryset(cls, queryset, info):
        queryset = queryset.select_related("profile")
        if info.context.user.is_anonymous:
            return queryset.filter(is_active=True)
        return queryset

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
