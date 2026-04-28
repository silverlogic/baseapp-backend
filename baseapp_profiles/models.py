import random
import string

import pghistory
import swapper
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.graphql.models import RelayModel
from baseapp_core.models import DocumentIdMixin, random_name_in
from baseapp_core.pghelpers import pghistory_register_default_track
from baseapp_core.plugins import shared_services
from baseapp_core.swapper import init_swapped_models
from baseapp_profiles.managers import ProfileManager

inheritances = [TimeStampedModel]
if apps.is_installed("baseapp_blocks"):
    from baseapp_blocks.models import BlockableModel

    inheritances.append(BlockableModel)


if apps.is_installed("baseapp_reports"):
    from baseapp_reports.models import ReportableModel

    inheritances.append(ReportableModel)


if apps.is_installed("baseapp_pages"):
    from baseapp_pages.models import PageMixin

    inheritances.append(PageMixin)

inheritances.append(DocumentIdMixin)
inheritances.append(RelayModel)


class AbstractProfile(*inheritances):
    class ProfileStatus(models.IntegerChoices):
        PUBLIC = 1, _("public")
        PRIVATE = 2, _("private")

        @property
        def description(self):
            return self.label

    name = models.CharField(_("name"), max_length=255, blank=True, null=True, editable=False)
    image = models.ImageField(
        _("image"), upload_to=random_name_in("profile_images"), blank=True, null=True
    )
    banner_image = models.ImageField(
        _("banner image"), upload_to=random_name_in("profile_banner_images"), blank=True, null=True
    )
    biography = models.TextField(_("biography"), blank=True, null=True)
    status = models.IntegerField(choices=ProfileStatus.choices, default=ProfileStatus.PUBLIC)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="profiles_owner",
        on_delete=models.CASCADE,
        verbose_name=_("owner"),
        db_constraint=False,
    )
    target_content_type = models.ForeignKey(
        ContentType,
        verbose_name=_("target content type"),
        blank=True,
        null=True,
        related_name="profiles",
        on_delete=models.CASCADE,
    )
    target_object_id = models.PositiveIntegerField(
        blank=True, null=True, verbose_name=_("target object id")
    )
    target = GenericForeignKey("target_content_type", "target_object_id")
    target.short_description = _("target")  # because GenericForeignKey doens't have verbose_name

    objects = ProfileManager()

    class Meta:
        abstract = True
        unique_together = [("target_content_type", "target_object_id")]
        permissions = [
            ("use_profile", _("can use profile")),
        ]
        swappable = swapper.swappable_setting("baseapp_profiles", "Profile")

    def __str__(self):
        return self.name or str(self.pk)

    def user_has_perm(self, user, perm=None):
        if not perm:
            Profile = swapper.load_model("baseapp_profiles", "Profile")
            profile_app_label = Profile._meta.app_label
            perm = f"{profile_app_label}.use_profile"
        return user.has_perm(perm, self)

    def get_all_users(self):
        User = get_user_model()
        return User.objects.filter(
            models.Q(profiles_owner=self) | models.Q(profile_members__profile=self)
        ).distinct()

    def create_url_path(self, profile_name: str | None = None):
        if service := shared_services.get("pages.url_path"):
            path_string = self.generate_url_path_str(profile_name=profile_name or self.name)
            service.create_url_path(
                self, path_string, language=None, is_active=True, generate_path_str=False
            )

    @classmethod
    def generate_url_path_str(cls, profile_name: str | None = None) -> str | None:
        if service := shared_services.get("pages.url_path"):
            name = profile_name or ""

            # Remove whitespaces
            name = name.translate(str.maketrans("", "", string.whitespace))

            # Make sure the name starts with a slash.
            name = name if name.startswith("/") else f"/{name}"

            # If name is an email (which would only occur if the user's first and last names are empty during user registration),
            # we'll remove the email domain and check if it's less than 8 characters. If it is, we'll add random digits to make it 8 characters.
            # OBS: We're not checking for any other special chars since we've blocked it in the RegisterSerializer in baseapp-auth. If
            # that changes, we should add a check here.
            name = name.split("@")[0]
            if len(name) < 8:
                path_string = name + "".join(random.choices(string.digits, k=8 - len(name)))
            else:
                path_string = name

            return service.generate_url_path_str(path_string)

        return None

    def check_if_member(self, user):
        return (
            self.__class__.objects.filter(pk=self.pk)
            .filter(models.Q(members__user=user) | models.Q(owner=user))
            .exists()
        )

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import ProfileObjectType

        return ProfileObjectType

    def save(self, *args, **kwargs):
        created = self._state.adding
        super().save(*args, **kwargs)

        if created:
            self.create_url_path()


class AbstractProfileUserRole(DocumentIdMixin, RelayModel):
    class ProfileRoles(models.IntegerChoices):
        ADMIN = 1, _("admin")
        MANAGER = 2, _("manager")

        @property
        def description(self):
            return self.label

    class ProfileRoleStatus(models.IntegerChoices):
        ACTIVE = 1, _("active")
        PENDING = 2, _("pending")
        INACTIVE = 3, _("inactive")

        @property
        def description(self):
            return self.label

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="profile_members",
        on_delete=models.CASCADE,
        verbose_name=_("user"),
    )
    profile = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        related_name="members",
        on_delete=models.CASCADE,
        verbose_name=_("profile"),
    )
    role = models.IntegerField(choices=ProfileRoles.choices, default=ProfileRoles.MANAGER)
    status = models.IntegerField(
        choices=ProfileRoleStatus.choices, default=ProfileRoleStatus.PENDING
    )

    class Meta:
        abstract = True
        unique_together = [("user", "profile")]
        swappable = swapper.swappable_setting("baseapp_profiles", "ProfileUserRole")

    def __str__(self):
        return f"{self.user} as {self.role} in {self.profile}"

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import ProfileUserRoleObjectType

        return ProfileUserRoleObjectType


def update_or_create_profile(instance, owner, profile_name):
    # TODO (profile): Review myabe the instance type before doing the rest.
    Profile = swapper.load_model("baseapp_profiles", "Profile")
    target_content_type = ContentType.objects.get_for_model(instance)

    profile, created = Profile.objects.update_or_create(
        owner=owner,
        target_content_type=target_content_type,
        target_object_id=instance.pk,
        defaults={"name": profile_name},
    )
    if created:
        # TODO (profile): Review if that's how we always connect instances to profiles.
        instance.profile = profile
        instance.save(update_fields=["profile"])


Profile, ProfileUserRole = init_swapped_models(
    [
        ("baseapp_profiles", "Profile"),
        ("baseapp_profiles", "ProfileUserRole"),
    ]
)


pghistory_register_default_track(
    Profile,
    pghistory.InsertEvent(),
    pghistory.UpdateEvent(),
    pghistory.DeleteEvent(),
)
