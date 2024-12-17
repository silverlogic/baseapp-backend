import uuid

import swapper
from baseapp_core.graphql.models import RelayModel
from baseapp_core.models import random_name_in
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_profiles.managers import ProfileManager

inheritances = [TimeStampedModel]
if apps.is_installed("baseapp_blocks"):
    from baseapp_blocks.models import BlockableModel

    inheritances.append(BlockableModel)


if apps.is_installed("baseapp_follows"):
    from baseapp_follows.models import FollowableModel

    inheritances.append(FollowableModel)

if apps.is_installed("baseapp_reports"):
    from baseapp_reports.models import ReportableModel

    inheritances.append(ReportableModel)

if apps.is_installed("baseapp_comments"):
    from baseapp_comments.models import CommentableModel

    inheritances.append(CommentableModel)

if apps.is_installed("baseapp_pages"):
    from baseapp_pages.models import PageMixin

    inheritances.append(PageMixin)

inheritances.append(RelayModel)


class AbstractProfile(*inheritances):
    class ProfileStatus(models.IntegerChoices):
        PUBLIC = 1, _("public")
        PRIVATE = 2, _("private")

        @property
        def description(self):
            return self.label

    name = models.CharField(_("name"), max_length=255, blank=True, null=True)
    image = models.ImageField(
        _("image"), upload_to=random_name_in("profile_images"), blank=True, null=True
    )
    banner_image = models.ImageField(
        _("banner image"), upload_to=random_name_in("profile_banner_images"), blank=True, null=True
    )
    biography = models.TextField(_("biography"), blank=True, null=True)

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

    status = models.IntegerField(choices=ProfileStatus.choices, default=ProfileStatus.PUBLIC)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="profiles_owner",
        on_delete=models.CASCADE,
        verbose_name=_("owner"),
        db_constraint=False,
    )

    objects = ProfileManager()

    class Meta:
        abstract = True
        unique_together = [("target_content_type", "target_object_id")]
        permissions = [
            ("use_profile", _("can use profile")),
        ]

    def __str__(self):
        return self.name or str(self.pk)

    def user_has_perm(self, user, perm=None):
        return user.has_perm(perm or "baseapp_profiles.use_profile", self)

    def get_all_users(self):
        User = get_user_model()
        return User.objects.filter(
            models.Q(profiles_owner=self) | models.Q(profile_members__profile=self)
        ).distinct()

    def generate_url_path(self, random=False):
        if random:
            return f"profile/{uuid.uuid4()}"
        return f"profile/{self.pk}"

    def create_url_path(self):
        from baseapp_pages.models import URLPath

        url_path = self.generate_url_path()
        if URLPath.objects.filter(path=url_path).exists():
            url_path = self.generate_url_path(random=True)
        self.url_paths.create(path=url_path, language=None, is_active=True)

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

    # def save(self, *args, **kwargs):
    #     created = self._state.adding
    #     super().save(*args, **kwargs)

    #     if created:
    #         self.create_url_path()


class ProfilableModel(models.Model):
    profile = models.OneToOneField(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        related_name="%(class)s",
        on_delete=models.CASCADE,
        verbose_name=_("profile"),
        null=True,
        blank=True,
    )

    class Meta:
        abstract = True


class Profile(AbstractProfile):
    class Meta(AbstractProfile.Meta):
        swappable = swapper.swappable_setting("baseapp_profiles", "Profile")


class AbstractProfileUserRole(RelayModel, models.Model):
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

    def __str__(self):
        return f"{self.user} as {self.role} in {self.profile}"

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import ProfileUserRoleObjectType

        return ProfileUserRoleObjectType


class ProfileUserRole(AbstractProfileUserRole):
    class Meta(AbstractProfileUserRole.Meta):
        swappable = swapper.swappable_setting("baseapp_profiles", "ProfileUserRole")
