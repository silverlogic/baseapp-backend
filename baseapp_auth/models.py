import swapper
from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.db.models import TextChoices
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel
from phonenumber_field.modelfields import PhoneNumberField

from baseapp_core.models import CaseInsensitiveEmailField

from .managers import UserManager


def use_relay_model():
    try:
        from baseapp_core.graphql.models import RelayModel

        return RelayModel
    except ImportError:
        return object


def use_profile_model():
    if apps.is_installed("baseapp_profiles"):
        from baseapp_profiles.models import ProfilableModel

        class UserProfilableModel(ProfilableModel):
            profile = models.OneToOneField(
                swapper.get_model_name("baseapp_profiles", "Profile"),
                related_name="%(class)s",
                on_delete=models.SET_NULL,
                verbose_name=_("profile"),
                null=True,
                blank=True,
            )

            class Meta:
                abstract = True

        return UserProfilableModel
    return object


class AbstractUser(PermissionsMixin, AbstractBaseUser, use_relay_model(), use_profile_model()):
    email = CaseInsensitiveEmailField(unique=True, db_index=True)
    is_email_verified = models.BooleanField(default=False)
    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)
    password_changed_date = models.DateTimeField(
        _("last date password was changed"), default=timezone.now
    )

    # Changing email
    new_email = CaseInsensitiveEmailField(blank=True)
    is_new_email_confirmed = models.BooleanField(
        default=False,
        help_text="Has the user confirmed they want an email change?",
    )

    # Profile
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    phone_number = PhoneNumberField(blank=True, null=True, unique=True)

    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_(
            "Designates whether this user should be treated as active. "
            "Unselect this instead of deleting accounts."
        ),
    )

    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can log into this admin site."),
    )

    objects = UserManager()

    preferred_language = models.CharField(max_length=9, choices=settings.LANGUAGES, default="en")

    USERNAME_FIELD = "email"

    class Meta:
        abstract = True
        verbose_name = _("user")
        verbose_name_plural = _("users")
        permissions = [
            ("view_all_users", _("can view all users")),
            ("view_user_email", _("can view user's email field")),
            ("view_user_phone_number", _("can view user's phone number field")),
            ("view_user_is_superuser", _("can view user's is_superuser field")),
            ("view_user_is_staff", _("can view user's is_staff field")),
            ("view_user_is_email_verified", _("can view user's is_email_verified field")),
            ("view_user_password_changed_date", _("can view user's password_changed_date field")),
            ("view_user_new_email", _("can view user's new_email field")),
            ("view_user_is_new_email_confirmed", _("can view user's is_new_email_confirmed field")),
        ]

    def __str__(self):
        return self.get_full_name()

    def get_full_name(self):
        names = [self.first_name, self.last_name]
        full_name = " ".join([name for name in names if name]).strip()
        return full_name or self.email

    @property
    def avatar(self):
        # TODO: deprecate
        return self.profile.image if self.profile_id else None

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import UserObjectType

        return UserObjectType

    def save(self, *args, **kwargs):
        if hasattr(self, "tracker"):
            with self.tracker:
                if self.tracker.has_changed("password"):
                    self.password_changed_date = timezone.now()
                super().save(*args, **kwargs)


class PasswordValidation(models.Model):
    class Validators(TextChoices):
        UserAttributeSimilarityValidator = (
            "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
            "User Attribute Similarity",
        )
        MinimumLengthValidator = (
            "django.contrib.auth.password_validation.MinimumLengthValidator",
            "Minimum Length",
        )
        CommonPasswordValidator = (
            "django.contrib.auth.password_validation.CommonPasswordValidator",
            "Common Password",
        )
        NumericPasswordValidator = (
            "django.contrib.auth.password_validation.NumericPasswordValidator",
            "Numeric Password",
        )
        MustContainCapitalLetterValidator = (
            "baseapp_auth.password_validators.MustContainCapitalLetterValidator",
            "Must Contain Capital Letter",
        )
        MustContainSpecialCharacterValidator = (
            "baseapp_auth.password_validators.MustContainSpecialCharacterValidator",
            "Must Contain Special Character",
        )

    name = models.CharField(max_length=255, choices=Validators.choices)
    options = models.JSONField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class SuperuserUpdateLog(TimeStampedModel):
    assigner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="superuser_assigner_logs",
        on_delete=models.CASCADE,
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="superuser_assignee_logs",
        on_delete=models.CASCADE,
    )
    made_superuser = models.BooleanField()
