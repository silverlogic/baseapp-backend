import swapper
from baseapp_core.graphql.models import RelayModel
from baseapp_core.models import random_name_in
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel


class AbstractProfile(TimeStampedModel, RelayModel):
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
        verbose_name=_("user"),
        db_constraint=False,
    )

    # members = models.ManyToManyField(
    #     settings.AUTH_USER_MODEL,
    #     related_name="profiles",
    #     through=swapper.get_model_name("baseapp_profiles", "Profile"),
    #     through_fields=("profile", "user"),
    # )

    class Meta:
        abstract = True

    def __str__(self):
        return self.name or str(self.pk)


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
    class Meta:
        swappable = swapper.swappable_setting("baseapp_profiles", "Profile")
        unique_together = [("target_content_type", "target_object_id")]
        permissions = [
            ("use_profile", _("can use profile")),
        ]


class AbstractProfileUserRole(models.Model):
    class ProfileRoles(models.IntegerChoices):
        ADMIN = 1, _("admin")
        MANAGER = 2, _("manager")

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

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.user} as {self.role} in {self.profile}"


class ProfileUserRole(AbstractProfileUserRole):
    class Meta:
        swappable = swapper.swappable_setting("baseapp_profiles", "ProfileUserRole")
        unique_together = [("user", "profile")]
