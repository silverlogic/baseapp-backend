import logging
import re

import pghistory
import pgtrigger
import swapper
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.signals import class_prepared
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.graphql.models import RelayModel
from baseapp_core.models import DocumentIdMixin, random_name_in
from baseapp_core.pghelpers import pghistory_register_default_track
from baseapp_core.plugins import shared_services
from baseapp_core.swapper import init_swapped_models
from baseapp_profiles.managers import ProfileManager
from baseapp_profiles.utils import pad_handle, to_ascii_handle

logger = logging.getLogger(__name__)


inheritances = []

if apps.is_installed("baseapp_pages"):
    from baseapp_pages.models import PageMixin

    inheritances.append(PageMixin)


class AbstractProfile(*inheritances, DocumentIdMixin, RelayModel, TimeStampedModel):
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
            # Build the handle (with owner-email fallback) then let the service
            # resolve uniqueness against existing rows before persisting.
            path_string = service.generate_url_path_str(self.generate_url_path(profile_name))
            service.create_url_path(
                self, path_string, language=None, is_active=True, generate_path_str=False
            )

    def generate_url_path(self, profile_name: str | None = None) -> str:
        """
        Build this profile's URL handle (with leading slash) from its display name.

        Uses `profile_name` when provided, otherwise `self.name`. The name is
        folded to a URL-safe ASCII handle (accents transliterated, emoji and other
        non-alphanumerics dropped). When the name yields no usable characters
        (e.g. an emoji-only name), it falls back to the local-part of the owner's
        email so the handle stays meaningful. The result is NOT collision-checked —
        `create_url_path` resolves uniqueness via the `pages.url_path` service.
        """
        name = profile_name if profile_name else (self.name or "")
        slug = to_ascii_handle(name)

        if not slug and self.owner_id:
            owner_email = getattr(self.owner, "email", "") or ""
            slug = to_ascii_handle(owner_email.split("@")[0])

        return pad_handle(slug)

    @classmethod
    def generate_url_path_str(cls, profile_name: str | None = None) -> str | None:
        """
        Suggest a free URL handle for `profile_name` (collision-resolved).

        Classmethod variant used to preview/validate a handle from an arbitrary
        string — there is no owner context here, so no email fallback, and no
        random-digit padding (that is only for name-derived handles, where a
        minimum length must be guaranteed). The returned path is the normalized
        handle with collision resolution applied. Returns `None` when the
        `pages.url_path` service is unavailable.
        """
        if service := shared_services.get("pages.url_path"):
            return service.generate_url_path_str(f"/{to_ascii_handle(profile_name or '')}")

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


class ProfilableModel(models.Model):
    """
    Abstract mixin for entities that act as first-class participants in the system —
    capable of writing comments, sending private messages, following other entities,
    and so on.

    Each concrete subclass gets a linked Profile row that holds public-facing
    metadata (name, avatar, URL path, etc.) and is the identity used across all
    social features.  Currently User and Organization are ProfilableModel subclasses.

    To wire up a new entity:
      1. Inherit from ProfilableModel.
      2. Set profile_name_sql to a SQL expression (using NEW.<col>) that produces
         the display name, e.g. "NEW.first_name || ' ' || NEW.last_name".
      3. Optionally set profile_owner_sql (e.g. "NEW.user_id") to have the INSERT
         trigger create and link the Profile automatically. Omit it when the
         owner is determined later by application logic.
      4. Run makemigrations.
    """

    profile = models.OneToOneField(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        related_name="%(class)s",
        on_delete=models.PROTECT,
        verbose_name=_("profile"),
        null=True,
        blank=True,
    )

    # Subclasses must define this as a SQL expression referencing NEW columns.
    # e.g. "NEW.first_name || ' ' || NEW.last_name" or "NEW.name"
    profile_name_sql = None

    # Subclasses that want automatic profile creation on INSERT must define this
    # as a SQL expression for the profile owner_id.
    # e.g. "NEW.id" for a self-owned model like User.
    # Leave as None to skip auto-creation (e.g. Organization, where the owner
    # is determined by application context at creation time).
    profile_owner_sql = None

    class Meta:
        abstract = True


def _columns_from_profile_name_sql(sql):
    """Extract column names referenced as NEW.<col> in a profile_name_sql expression."""
    return re.findall(r"NEW\.(\w+)", sql) or None


class UpdateProfileNameFunc(pgtrigger.Func):
    """
    Reusable pgtrigger function that updates profile.name whenever a ProfilableModel row is updated.
    SQL values are captured at class_prepared time (real model) so that render() works
    correctly when called with migration state models (which lack custom class attributes).
    Leading/trailing whitespace is trimmed from the resulting name.
    """

    def __init__(self, func="", *, profile_name_sql, profile_column):
        super().__init__(func)
        self._profile_name_sql = profile_name_sql
        self._profile_column = profile_column

    def render(self, **kwargs) -> str:
        Profile = swapper.load_model("baseapp_profiles", "Profile")
        profile_table = Profile._meta.db_table
        return f"""
            IF NEW.{self._profile_column} IS NOT NULL THEN
                UPDATE {profile_table} SET name = TRIM(COALESCE({self._profile_name_sql}, '')), modified = NOW() WHERE id = NEW.{self._profile_column};
            END IF;
            RETURN NULL;
        """


def _python_default_to_sql(default):
    """
    Convert a Python value (from field.get_default()) to a SQL literal safe for embedding
    in a raw trigger INSERT statement.
    Returns None if the value cannot be safely converted.
    """
    import json as _json

    if isinstance(default, bool):
        return "TRUE" if default else "FALSE"
    elif isinstance(default, int):
        return str(default)
    elif isinstance(default, float):
        return str(default)
    elif isinstance(default, str):
        return "'{}'".format(default.replace("'", "''"))
    elif isinstance(default, (dict, list)):
        serialized = _json.dumps(default, separators=(",", ":")).replace("'", "''")
        return "'{}'::jsonb".format(serialized)
    return None


class CreateProfileFunc(pgtrigger.Func):
    """
    Reusable pgtrigger function that creates a Profile on INSERT of a ProfilableModel row
    and links it back by setting profile_id on the source row.
    Only fires when profile_id is not already set on the new row.
    SQL values are captured at class_prepared time so that render() works with state models.

    render() dynamically builds the INSERT column list from the live Profile model so that
    extra NOT NULL fields added by optional mixins (e.g. CommentableModel) are included with
    their Python defaults — no manual maintenance required.
    """

    def __init__(
        self,
        func="",
        *,
        profile_name_sql,
        profile_owner_sql,
        profile_column,
        app_label,
        model_name,
        self_table,
        pk,
    ):
        super().__init__(func)
        self._profile_name_sql = profile_name_sql
        self._profile_owner_sql = profile_owner_sql
        self._profile_column = profile_column
        self._app_label = app_label
        self._model_name = model_name
        self._self_table = self_table
        self._pk = pk

    def render(self, **kwargs) -> str:
        Profile = swapper.load_model("baseapp_profiles", "Profile")
        profile_table = Profile._meta.db_table
        content_type_table = ContentType._meta.db_table

        # Escape single quotes in app_label/model_name as a defensive measure
        # (Django enforces these are valid identifiers, but belt-and-suspenders).
        safe_app_label = self._app_label.replace("'", "''")
        safe_model_name = self._model_name.replace("'", "''")

        # Columns and SQL values we always provide explicitly.
        explicit = {
            "owner_id": self._profile_owner_sql,
            "target_content_type_id": (
                f"(SELECT id FROM {content_type_table}"
                f" WHERE app_label = '{safe_app_label}' AND model = '{safe_model_name}')"
            ),
            "target_object_id": f"NEW.{self._pk}",
            "name": f"TRIM(COALESCE({self._profile_name_sql}, ''))",
            "created": "NOW()",
            "modified": "NOW()",
        }

        # Dynamically add any extra NOT NULL columns that have Python-level defaults
        # (e.g. blockers_count from optional mixins).
        for field in Profile._meta.fields:
            col = field.column
            if col in explicit or field.primary_key or field.null:
                continue
            if not field.has_default():
                continue
            sql_val = _python_default_to_sql(field.get_default())
            if sql_val is None:
                raise ValueError(
                    f"CreateProfileFunc: cannot convert the default value of NOT NULL field "
                    f"'{col}' ({type(field).__name__}) to a SQL literal. "
                    f"Add explicit handling for {type(field.get_default()).__name__} in "
                    f"_python_default_to_sql or make the field nullable."
                )
            explicit[col] = sql_val

        columns = ", ".join(explicit.keys())
        values = ", ".join(explicit.values())

        return f"""
            IF NEW.{self._profile_column} IS NULL THEN
                WITH new_profile AS (
                    INSERT INTO {profile_table} ({columns})
                    VALUES ({values})
                    -- Conflicts arise when a Profile for this object already exists
                    -- (e.g. seeded by a migration or a prior trigger run).  Refresh
                    -- owner, name, and modified so the profile stays consistent with
                    -- the current row rather than silently retaining stale values.
                    ON CONFLICT (target_content_type_id, target_object_id) DO UPDATE
                        SET owner_id = EXCLUDED.owner_id,
                            name     = EXCLUDED.name,
                            modified = EXCLUDED.modified
                    RETURNING id
                )
                UPDATE {self._self_table} SET {self._profile_column} = (SELECT id FROM new_profile) WHERE {self._pk} = NEW.{self._pk};
            END IF;
            RETURN NULL;
        """


def update_profile_name_trigger(profile_name_sql, profile_column):
    """
    Trigger to automatically update profile.name when a ProfilableModel row is updated.
    The columns referenced in `profile_name_sql` (as NEW.<col>) are automatically used
    to scope the trigger to only fire when those columns change.
    """
    columns = _columns_from_profile_name_sql(profile_name_sql)
    operation = pgtrigger.UpdateOf(*columns) if columns else pgtrigger.Update
    return pgtrigger.Trigger(
        name="update_profile_name",
        level=pgtrigger.Row,
        when=pgtrigger.After,
        operation=operation,
        func=UpdateProfileNameFunc(
            profile_name_sql=profile_name_sql,
            profile_column=profile_column,
        ),
    )


def create_profile_trigger(
    *, profile_name_sql, profile_owner_sql, profile_column, app_label, model_name, self_table, pk
):
    """
    Trigger to automatically create a Profile and link it back to the ProfilableModel instance on INSERT.
    """
    return pgtrigger.Trigger(
        name="create_profile",
        level=pgtrigger.Row,
        when=pgtrigger.After,
        operation=pgtrigger.Insert,
        func=CreateProfileFunc(
            profile_name_sql=profile_name_sql,
            profile_owner_sql=profile_owner_sql,
            profile_column=profile_column,
            app_label=app_label,
            model_name=model_name,
            self_table=self_table,
            pk=pk,
        ),
    )


@receiver(class_prepared)
def add_profilable_triggers(sender, **kwargs):
    """
    Auto-add pgtriggers to every concrete ProfilableModel subclass that defines `profile_name_sql`.
    - Always adds the UPDATE trigger to keep profile.name in sync.
    - Also adds the INSERT trigger when `profile_owner_sql` is defined, enabling automatic
      profile creation without a Python-level signal.

    All SQL values are extracted from the live sender model here so that the Func objects
    carry them as plain strings — safe to use even when pgtrigger later calls render() with
    a migration state model (which lacks custom class attributes).
    """
    if not issubclass(sender, ProfilableModel):
        return
    if sender._meta.abstract or sender._meta.proxy:
        return
    if getattr(sender._meta, "swapped", None):
        return

    profile_name_sql = getattr(sender, "profile_name_sql", None)
    if not profile_name_sql:
        return

    if not hasattr(sender._meta, "triggers"):
        sender._meta.triggers = []

    existing = [t.name for t in sender._meta.triggers]
    profile_column = sender._meta.get_field("profile").column

    if "update_profile_name" not in existing:
        sender._meta.triggers.append(
            update_profile_name_trigger(
                profile_name_sql=profile_name_sql,
                profile_column=profile_column,
            )
        )
    else:
        logger.warning(
            "add_profilable_triggers: skipping 'update_profile_name' trigger for %s.%s "
            "because a trigger with that name already exists.",
            sender._meta.app_label,
            sender._meta.model_name,
        )

    profile_owner_sql = getattr(sender, "profile_owner_sql", None)
    if profile_owner_sql:
        if "create_profile" not in existing:
            sender._meta.triggers.append(
                create_profile_trigger(
                    profile_name_sql=profile_name_sql,
                    profile_owner_sql=profile_owner_sql,
                    profile_column=profile_column,
                    app_label=sender._meta.app_config.label,
                    model_name=sender._meta.model_name,
                    self_table=sender._meta.db_table,
                    pk=sender._meta.pk.column,
                )
            )
        else:
            logger.warning(
                "add_profilable_triggers: skipping 'create_profile' trigger for %s.%s "
                "because a trigger with that name already exists.",
                sender._meta.app_label,
                sender._meta.model_name,
            )


class AbstractProfileUserRole(DocumentIdMixin, RelayModel, models.Model):
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
        DECLINED = 4, _("declined")
        EXPIRED = 5, _("expired")

        @property
        def description(self):
            return self.label

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="profile_members",
        on_delete=models.CASCADE,
        verbose_name=_("user"),
        null=True,
        blank=True,
    )
    email = models.EmailField(_("email"), null=True, blank=True)
    profile = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        related_name="members",
        on_delete=models.CASCADE,
        verbose_name=_("profile"),
    )
    role = models.IntegerField(choices=ProfileRoles.choices, default=ProfileRoles.MANAGER)
    status = models.IntegerField(
        choices=ProfileRoleStatus.choices, default=ProfileRoleStatus.INACTIVE
    )

    invited_email = models.EmailField(
        null=True,
        blank=True,
        verbose_name=_("invited email"),
        help_text=_("Email address invitation was sent to (for pending invitations)"),
    )
    invitation_token = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        unique=True,
        verbose_name=_("invitation token"),
        help_text=_("Unique token for accepting invitation"),
    )
    invited_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("invited at"),
        help_text=_("When the invitation was sent"),
    )
    invitation_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("invitation expires at"),
        help_text=_("When the invitation expires"),
    )
    responded_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("responded at"),
        help_text=_("When the user accepted or declined"),
    )

    class Meta:
        abstract = True
        unique_together = [("user", "profile")]
        swappable = swapper.swappable_setting("baseapp_profiles", "ProfileUserRole")
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "invited_email"],
                name="unique_profile_invited_email",
                condition=models.Q(invited_email__isnull=False),
            ),
        ]

    def is_invitation_expired(self):
        from django.utils import timezone

        if not self.invitation_expires_at:
            return False
        return timezone.now() > self.invitation_expires_at

    def generate_invitation_token(self):
        from django.utils.crypto import get_random_string

        token = get_random_string(length=64)
        self.invitation_token = token
        return token

    def __str__(self):
        return f"{self.user} as {self.role} in {self.profile}"

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import ProfileUserRoleObjectType

        return ProfileUserRoleObjectType


def update_or_create_profile(instance, owner, profile_name):
    Profile = swapper.load_model("baseapp_profiles", "Profile")
    target_content_type = ContentType.objects.get_for_model(instance)

    profile, created = Profile.objects.update_or_create(
        owner=owner,
        target_content_type=target_content_type,
        target_object_id=instance.pk,
        defaults={"name": profile_name},
    )
    if created:
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
    exclude=[
        "modified",
        "created",
    ],
)
