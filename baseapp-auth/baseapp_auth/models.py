from baseapp_core.models import CaseInsensitiveEmailField
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.db.models import TextChoices
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from .managers import UserManager


class AbstractUser(PermissionsMixin, AbstractBaseUser):
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

    USERNAME_FIELD = "email"

    class Meta:
        abstract = True
        verbose_name = _("user")
        verbose_name_plural = _("users")

    def __str__(self):
        return self.get_full_name()

    def get_short_name(self):
        return self.email

    def get_full_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}".strip()
        return self.email

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
        on_delete=models.PROTECT,
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="superuser_assignee_logs",
        on_delete=models.CASCADE,
    )
    made_superuser = models.BooleanField()
