# BaseApp Profiles

Reusable app for profiles, their URL paths, members/roles, and metadata. A `Profile` is the public-facing identity (name, avatar, banner, biography, URL handle) attached to any `ProfilableModel` (User, Organization, …), and it is the actor/target other social features (follows, blocks, reports, comments, chats) hang off of.

`baseapp_profiles` follows the [plugin architecture](../baseapp_core/plugins/README.md): it registers itself as a plugin for settings aggregation and wires its middleware, permissions backend, GraphQL roots, shared services and shared GraphQL interfaces through the registry — no direct cross-package imports.

## How to install

Install the package with `pip install baseapp-backend`.

If you want to develop, [install using this other guide](#how-to-develop).

## How to setup

The package registers itself as a plugin (see `baseapp_profiles.plugin:ProfilesPlugin`), so most wiring goes through `plugin_registry`.

1. Add `baseapp_profiles` to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    "baseapp_profiles",
    # ...
]
```

2. Wire the middleware slot — `CurrentProfileMiddleware` must come **after** `django.contrib.auth.middleware.AuthenticationMiddleware`:

```python
MIDDLEWARE = [
    # ... AuthenticationMiddleware above ...
    *plugin_registry.get("MIDDLEWARE", "baseapp_profiles"),
    # ...
]
```

3. Wire the auth backend slot — `ProfilesPermissionsBackend` is contributed via the registry:

```python
AUTHENTICATION_BACKENDS = [
    # ...
    *plugin_registry.get("AUTHENTICATION_BACKENDS", "baseapp_profiles"),
    # ...
]
```

4. Make sure your project's `graphql.py` composes the schema via `plugin_registry.get_all_graphql_*()` so `ProfilesQueries` and `ProfilesMutations` are picked up automatically. The GraphQL middleware slot (`GRAPHENE__MIDDLEWARE`, also keyed `baseapp_profiles`) carries the GraphQL-side `CurrentProfileMiddleware`.

5. Define the concrete models (see [models](#models)) and point the swapper settings at them:

```python
BASEAPP_PROFILES_PROFILE_MODEL = "profiles.Profile"
BASEAPP_PROFILES_PROFILEUSERROLE_MODEL = "profiles.ProfileUserRole"
```

Run `./manage.py makemigrations` / `./manage.py migrate` after defining them.

## Models

Both models are abstract + swappable, and the package ships **no** concrete models or migrations — your project must subclass the abstracts in a local app and point the swapper settings at them (see [How to develop](#how-to-develop)).

| Abstract | Concrete reference | Purpose |
|---|---|---|
| `AbstractProfile` | `Profile` | Public identity: `name` (trigger-maintained), `image`, `banner_image`, `biography`, `status` (public/private), `owner` FK (nullable, see [ownerless profiles](#ownerless-profiles)), and a generic `target`. Inherits `DocumentIdMixin`, so any profile can be the target of follows/blocks/reports/comments/chats. |
| `AbstractProfileUserRole` | `ProfileUserRole` | Membership join row (`profile.members`): a user's `role` (manager/admin/…) and `status` (pending/active/…) on a profile. The same row carries the email invitation that led to it and its audit trail — see [Members and invitations](#members-and-invitations). |

`Profile` also inherits `PageMixin` (when `baseapp_pages` is installed) so it owns URL paths.

## ProfilableModel

`ProfilableModel` is an abstract model mixin that automatically keeps a `Profile` in sync with your model via PostgreSQL triggers — no Python signals required.

### What it does

- **On INSERT**: if `profile_owner_sql` is defined, a trigger creates a `Profile` row and links it back to your model via the `profile` FK (uses `ON CONFLICT … DO UPDATE` so it is safe to re-run).
- **On UPDATE**: a trigger updates `profile.name` whenever the columns referenced in `profile_name_sql` change.

Both triggers are registered automatically at class-definition time — no manual wiring needed.

### Usage

Inherit from `ProfilableModel` and define at least `profile_name_sql`:

```python
from baseapp_profiles.models import ProfilableModel

class MyModel(ProfilableModel):
    # Required: SQL expression using NEW.<col> references that produces the profile name.
    # The framework automatically wraps the whole expression with TRIM(COALESCE(..., ''))
    # so a fully-NULL result never reaches profile.name.
    profile_name_sql = "NEW.first_name || ' ' || NEW.last_name"

    # Optional: SQL expression for the profile owner_id on INSERT.
    # When provided, the trigger creates and links a Profile automatically.
    # Omit when ownership is determined later by application logic (e.g. Organization).
    profile_owner_sql = "NEW.id"
```

If any of the referenced columns are **nullable**, wrap them individually with `COALESCE` to prevent a single NULL from making the entire expression NULL (PostgreSQL: `NULL || anything = NULL`):

```python
    # first_name and last_name are nullable on this model
    profile_name_sql = "COALESCE(NEW.first_name, '') || ' ' || COALESCE(NEW.last_name, '')"
```

After adding or changing these attributes, run `makemigrations` to capture the updated trigger SQL:

```bash
./manage.py makemigrations
```

### Signals

Two post-save signal handlers are available for features that still require Python-level logic:

- **`create_profile_url_path`** — calls `profile.create_url_path()` after creation when `baseapp_pages` is installed. Connect it if your model needs URL paths:

  ```python
  from django.db.models.signals import post_save
  from baseapp_profiles.signals import create_profile_url_path

  post_save.connect(create_profile_url_path, sender=MyModel)
  ```

- **`update_user_profile`** *(deprecated)* — fallback for projects that have not yet added `profile_owner_sql`. Creates the profile via Python if the trigger did not run. New projects should use `profile_owner_sql` instead.

## URL paths

When `baseapp_pages` is installed, each profile owns a URL handle (e.g. `/jonathandoe`). Handles are always lowercase. Handle generation lives on the model; uniqueness/collision resolution lives in the `pages.url_path` shared service.

- `profile.generate_url_path(profile_name=None)` — builds the handle (with leading slash) from `profile_name` or `self.name`. The name is folded to a lowercase URL-safe ASCII handle via `baseapp_profiles.utils.to_ascii_handle` (accents transliterated and case folded — `Döe` → `doe`; emoji and other non-alphanumerics dropped). When the name folds to nothing (e.g. an emoji-only name), it falls back to the local-part of the owner's email; as a last resort `pad_handle` pads with random digits to an 8-char minimum. The result is **not** collision-checked.
- `profile.create_url_path(profile_name=None)` — builds the handle, then asks the `pages.url_path` service to resolve uniqueness (appending a numeric suffix when taken) before persisting the `URLPath`.
- `Profile.generate_url_path_str(profile_name)` *(classmethod)* — collision-resolved suggestion for an arbitrary string (no owner context, so no email fallback). Used by `ProfileUpdateSerializer.validate_url_path` to suggest a free handle when the requested one is taken.

`Profile.save()` calls `create_url_path()` on creation, and the `create_profile_url_path` signal does the same for `ProfilableModel` subclasses.

## GraphQL

### Queries (`ProfilesQueries`)

| Field | Description |
|---|---|
| `profile(id)` | RelayNode fetch of a single `Profile`. `get_node` enforces `view_profile`. |
| `allProfiles` | Filterable connection of profiles (`ProfileFilter`). Non-superusers only see `PUBLIC` profiles plus their own. |

### Mutations (`ProfilesMutations`)

| Field | Purpose |
|---|---|
| `profileCreate` | Create a profile (optionally targeting another object via `target`). |
| `profileUpdate` | Edit name, images, biography, phone, and URL handle (`url_path`). |
| `profileDelete` | Delete a profile. |
| `profileUserRoleCreate` | Add existing users as ACTIVE members. |
| `profileUserRoleUpdate` | Change a member's role (refuses to demote the last admin where [guarded](#last-admin-guard)). |
| `profileUserRoleDelete` | Remove a member (same guard). For someone who has not accepted yet, it cancels their invitation (`invitation_cancelled`, kept as CANCELLED with history on). |
| `profileMemberDeactivate` / `profileMemberReactivate` | Deactivate a member (keeps the row, records `deactivatedAt`/`deactivatedBy`, revokes access) or restore them. |
| `profileSendInvitation` | Invite by email in bulk: `emails` and/or `invitees` (`{email, firstName, lastName}`), `role`, optional `message`. Returns the rows, `emailsSent` and `emailsHeld`. |
| `profileResendInvitation` | Send a pending or expired invitation again with a fresh token. |
| `profileCancelInvitation` | Withdraw a pending invitation (marked CANCELLED with history on, deleted otherwise). |
| `profileAcceptInvitation` / `profileDeclineInvitation` | Respond as the signed-in invitee. |
| `profileAcceptInvitationWithSignup` | Accept without an account by choosing a password (opt-in, see below). |

| Query | Description |
|---|---|
| `profileInvitation(token)` | The invitation row for its token (members-only fields stay hidden). |
| `profileInvitationPreview(token)` | Public summary for an acceptance page: `profileName`, `invitedEmail`, `role`, `status`, `expiresAt`. |

### Shared GraphQL interfaces

Profiles **publishes** two interfaces via the registry — consume them by name (no direct import):

- `ProfileInterface` — exposes a single `profile` field for objects that have an associated profile.
- `ProfilesInterface` — exposes a `profiles` connection for objects that have many.

```python
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.plugins import graphql_shared_interfaces


class MyObjectType(DjangoObjectType):
    class Meta:
        interfaces = graphql_shared_interfaces.get(RelayNode, "ProfileInterface")
        model = MyModel
```

`ProfileObjectType` itself **consumes** interfaces published by other packages, resolved by name so they degrade gracefully when the package is absent: `ProfileActivityLogInterface`, `PageInterface`, `FollowsInterface`, `ReportsInterface`, `BlocksInterface`, `ChatRoomsInterface` (plus `PermissionsInterface`, which comes from the always-present `baseapp_core`).

To avoid N+1 on those interfaces' count fields, `BaseProfileObjectType.pre_optimization_hook` annotates the queryset through each metadata service it finds (`commentable_metadata`, `followable_metadata`, `reportable_metadata`). A project subclassing `BaseProfileObjectType` must preserve this hook.

## Shared services & serializers

### Provided

- **`profiles.graphql`** (`GraphQLProfileService`) — lets other packages obtain the (possibly swapped) Profile ObjectType / connection edge and create a profile from a mutation without importing `baseapp_profiles` directly:

  ```python
  from baseapp_core.plugins import shared_services

  if service := shared_services.get("profiles.graphql"):
      ObjectType = service.get_profile_object_type()
      edge = service.create_profile_from_mutation(info, target_instance, data)
  ```

- **`profiles.jwt_profile`** (shared *serializer*, `JWTProfileSerializer`) — registered via `register_shared_serializers`; consumed by `baseapp_auth` to embed the current profile in the JWT/user payload.

### Consumed

All optional — behaviour degrades gracefully when the providing package is absent:

- `pages.url_path` — URL handle creation / collision resolution (see [URL paths](#url-paths)).
- `commentable_metadata` / `followable_metadata` / `reportable_metadata` — queryset annotations for the corresponding interface count fields.

### Optional packages

`baseapp_blocks`, `baseapp_follows`, `baseapp_reports`, `baseapp_comments`, `baseapp_pages`, `baseapp.activity_log`, `baseapp_chats` — each enriches `ProfileObjectType` when installed.

## Middleware

`CurrentProfileMiddleware` reads the `Current-Profile` request header (a relay id); when present and the user may use that profile, it sets `request.user.current_profile`, otherwise it defaults to `request.user.profile`. Many resolvers and mutations (e.g. blocks/follows actor disambiguation) rely on `current_profile`.

## Members and invitations

A `ProfileUserRole` row is both a membership and the email invitation behind it. An
invitation is a row with `invited_email` and an `invitation_token`; accepting it turns the
same row into an ACTIVE membership.

| Status | Meaning | Open? |
|---|---|---|
| `PENDING` | Invitation sent (or held for review), not answered yet | yes |
| `ACTIVE` | Member with access | yes |
| `INACTIVE` | Deactivated member: keeps the row, reaches nothing | yes |
| `DECLINED` / `EXPIRED` / `CANCELLED` | Invitation history | no |

A person has at most one *open* row per profile (`ProfileUserRole.open_statuses()`); the
database enforces it with two conditional unique constraints. Closed rows may repeat.
`ProfileUserRole.objects` adds `.open()`, `.closed()`, `.memberships()`, `.invitations()`
and `.overdue()`.

Invitation rows also record `invited_first_name`, `invited_last_name`, `message`,
`invited_by`, `sent_count` and `last_sent_at`; memberships record `deactivated_at` and
`deactivated_by` (also set when an invitation is cancelled).

### Services

The GraphQL mutations and REST views are thin wrappers over plain functions you can call
from admin actions, importers, commands or your own API. They check business rules, not
permissions — the caller decides who may act — and raise
`baseapp_profiles.exceptions.ProfileMembershipError` with a stable `code`.

```python
from baseapp_profiles.services.invitations import Invitee, send_invitations

result = send_invitations(
    profile,
    [Invitee("ann@example.com", "Ann", "Lee"), "bob@example.com"],
    role=ProfileUserRole.ProfileRoles.ADMIN,
    invited_by=request.user,
    message="Welcome to the team",
)
result.invitations, result.emails_sent, result.held
```

| `baseapp_profiles.services.invitations` | |
|---|---|
| `send_invitations(profile, invitees, *, role=None, invited_by=None, message="")` | Bulk invite (emails, `Invitee`s or dicts); all-or-nothing on conflicts. Returns `SentInvitations`. |
| `resend_invitation(invitation, *, by=None)` | New token and expiry. With history on, an expired invitation stays EXPIRED and a new row is opened. |
| `release_invitation(invitation, *, by=None)` | Send an invitation the pre-send hook held. |
| `cancel_invitation(invitation, *, by=None)` | Withdraw a PENDING invitation. |
| `accept_invitation(token, user)` / `decline_invitation(token, user)` | Respond as a signed-in user, who must be the invitee. |
| `accept_invitation_with_signup(token, *, password, first_name=None, last_name=None)` | Anonymous accept, see below. |
| `lookup_invitation(token)` | `PublicInvitation(profile_name, invited_email, role, status, expires_at)` or `None`. |
| `expire_invitations(now=None)` | Mark overdue PENDING rows EXPIRED; returns the count. |

| `baseapp_profiles.services.members` | |
|---|---|
| `change_member_role(membership, role, *, by=None)` | Change the role (last-admin guard on demotion). |
| `deactivate_member(membership, *, by=None)` / `reactivate_member(...)` | ACTIVE ⇄ INACTIVE with the audit fields. |
| `remove_member(membership, *, by=None)` | Delete the row (last-admin guard). |
| `validate_role(role)` | Refuse a role outside `assignable_roles()`. |

Error codes: `invalid_input`, `invalid_token`, `invalid_status`, `already_member`,
`duplicate_invitation`, `expired_invitation`, `cancelled_invitation`, `already_responded`,
`wrong_user`, `cannot_add_owner`, `last_admin`, `signup_disabled`, `user_exists`,
`account_inactive`, `invalid_password`, `invalid_invitation`.

### Settings

Every default keeps the behaviour projects had before these settings existed.

| Setting | Default | Effect |
|---|---|---|
| `BASEAPP_PROFILES_INVITATION_KEEP_HISTORY` | `False` | Keep invitation history: cancel marks the row CANCELLED instead of deleting it, and inviting an email again opens a new row instead of reusing the declined/expired/cancelled one. |
| `BASEAPP_PROFILES_INVITATION_SIGNUP_ENABLED` | `False` | Allow anonymous accept-with-signup. |
| `BASEAPP_PROFILES_INVITATION_SIGNUP_CAN_REACTIVATE` | `None` | Dotted path to (or a) `callable(user, invitation) -> bool`: may accept-with-signup reactivate this inactive account? `None` allows only accounts that never signed in. Staff and superusers are always refused. |
| `BASEAPP_PROFILES_INVITATION_MAX_PER_SEND` | `None` | Most invitations one send (GraphQL, REST or `send_invitations`) may contain; `None` means no limit. |
| `BASEAPP_PROFILES_INVITATION_ASYNC_SEND` | `False` | Send invitation emails from the `send_invitation_email_task` Celery task, queued on commit. While Celery runs eagerly they are sent inline. |
| `BASEAPP_PROFILES_INVITATION_PRE_SEND_HOOK` | `None` | Dotted path to (or a) `callable(invitation) -> bool`; `True` holds the email. |
| `BASEAPP_PROFILES_PROTECT_LAST_ADMIN` | `False` | Apply the last-admin guard to profiles that have an owner too. |
| `BASEAPP_PROFILES_INVITATION_PUBLIC_RATE` | `"30/hour"` | Per-IP rate of the public REST token endpoints (`None` disables). |
| `INVITATION_EXPIRATION_DAYS` | `7` | Lifetime of an invitation. |

### Invitation history

With `BASEAPP_PROFILES_INVITATION_KEEP_HISTORY` on, every invitation stays on record:
declining, expiring or cancelling closes the row, and a later invitation to the same
person is a new row. History lives on `ProfileUserRole` itself rather than in a separate
event table, so it needs no extra model to swap, the members connection and the REST
invitations list can show it with a status filter, and each historical row still has its
role, message, sender and send count. The uniqueness that used to cover every row now
covers open rows only.

With history on, the profile's `members` connection lists open rows (members and pending
invitations) unless the client passes `status` (for example `members(status: DECLINED)`),
and `profileUserRoleUpdate` / `profileUserRoleDelete` only act on a person's open row, so
past invitations cannot be edited or deleted through them.

Off (the default), a person keeps a single row per profile, as before: cancel deletes it
and a new invitation reopens it.

### Accepting by signing up

With `BASEAPP_PROFILES_INVITATION_SIGNUP_ENABLED` on, an invitee without an account
accepts by choosing a password (`profileAcceptInvitationWithSignup`, or
`POST /profile-invitations/by-token/{token}/accept-with-signup`). The account is created
for the invited email — or an existing *inactive* account is activated (see below) — the
password is checked against `AUTH_PASSWORD_VALIDATORS`, `first_name`/`last_name` are set when given,
and `is_email_verified` is set when the user model has it (the token reached that
inbox). An email with an active account gets `user_exists` and must sign in and accept.
The client signs in with the returned email and the chosen password.

Reactivation is guarded. Holding the token only proves the invitee controls the inbox, and
anyone signed in can invite any address to a profile they own, so a deactivated user could
otherwise invite themselves and come back with a password of their choosing. By default
only an inactive account that has **never signed in** (one created ahead of time, by an
import for instance) is activated; any other gets `account_inactive`. Staff and superuser
accounts are never reactivated. To allow more — say, accounts your project deactivates
pending a first invitation — set `BASEAPP_PROFILES_INVITATION_SIGNUP_CAN_REACTIVATE`:

```python
# settings.py
BASEAPP_PROFILES_INVITATION_SIGNUP_CAN_REACTIVATE = "apps.members.invitations.can_reactivate"

# apps/members/invitations.py
def can_reactivate(user, invitation) -> bool:
    return not user.is_banned
```

### Sending, holding and expiring

Emails are sent inline after the invitations are saved, or — with
`BASEAPP_PROFILES_INVITATION_ASYNC_SEND` — from a Celery task queued on commit. A failed
email is logged and leaves the invitation in place; `sent_count` and `last_sent_at` only
count emails that went out.

A project can gate invitations behind a review with the pre-send hook:

```python
# settings.py
BASEAPP_PROFILES_INVITATION_PRE_SEND_HOOK = "apps.members.invitations.needs_review"

# apps/members/invitations.py
def needs_review(invitation) -> bool:
    if invitation.invited_email.endswith("@partner.example"):
        return False
    ReviewRequest.objects.get_or_create(invitation=invitation)
    return True  # hold it


# later, once approved
from baseapp_profiles.services.invitations import release_invitation

release_invitation(review.invitation, by=reviewer)
```

A held invitation stays PENDING without an expiry date, so it cannot lapse while it waits;
`release_invitation` starts the clock and sends it. A hook that raises holds the
invitation. Resends ask the hook again.

Overdue invitations are marked EXPIRED lazily when someone responds, and by the
`baseapp_profiles.tasks.expire_invitations` task. The plugin contributes an hourly beat
entry; merge `plugin_registry.get_all_celery_schedules()` into `CELERY_BEAT_SCHEDULE` to
run it.

### Signals

`baseapp_profiles.signals` sends these once the transaction commits, with `sender` the
concrete `ProfileUserRole` model and `instance` the row:

| Signal | Extra kwargs |
|---|---|
| `invitation_sent` | `inviter` |
| `invitation_accepted` | `user`, `created_user` (signed up while accepting) |
| `invitation_declined` | `user` |
| `invitation_cancelled` | `by` (with history off the row is already deleted) |
| `invitation_expired` | — |
| `member_role_changed` | `old_role`, `new_role`, `by` |
| `member_deactivated` / `member_reactivated` | `by` |
| `member_removed` | `pk` (the deleted row's), `by` |

### Last-admin guard

Demoting, deactivating or removing the last active ADMIN of a profile is refused with
`last_admin` when the profile has no owner (otherwise nobody could manage it), and for
every profile when `BASEAPP_PROFILES_PROTECT_LAST_ADMIN` is on.

### Ownerless profiles

`Profile.owner` is nullable, so a profile — typically an organization's — can be run
entirely by its ADMIN members. On an ownerless profile, active ADMINs stand in for the
owner: they get `change_profile` and `delete_profile` as well as member management, and a
private ownerless profile is listed (`allProfiles`) for its active members. Profiles with
an owner keep owner-only `change_profile` / `delete_profile`. Compare owners with
`profile.is_owned_by(user)`, never `profile.owner_id == user.id`: an anonymous user's id is
`None` too.

### Project roles

The default roles are ADMIN and MANAGER. To add roles, redeclare the nested
`ProfileRoles` on your concrete model and run `makemigrations`:

```python
class ProfileUserRole(AbstractProfileUserRole):
    class ProfileRoles(models.IntegerChoices):
        ADMIN = 1, _("admin")
        MANAGER = 2, _("manager")
        VIEWER = 3, _("viewer")

        @property
        def description(self) -> str:
            return self.label

    class Meta(AbstractProfileUserRole.Meta):
        pass
```

The `role` field picks the new choices up automatically (for `full_clean`, the admin and
`get_role_display()`), as do `assignable_roles()`, the GraphQL `ProfileRoles` enum and the
REST serializers. Keep `ADMIN = 1`: the permission backend and the last-admin guard rely
on it. Override `assignable_roles()` to declare a role without handing it out yet.

### REST

`baseapp_profiles.rest_framework.routers.profiles_router` is not mounted by the plugin;
include it in your v1 URLs:

```python
from baseapp_profiles.rest_framework.routers import profiles_router

v1_urlpatterns = [
    *plugin_registry.get_all_v1_urlpatterns(),
    re_path(r"", include(profiles_router.urls)),
]
```

The members and invitations endpoints act on the **current profile**: send its relay id in
the `Current-Profile` header (see `CurrentProfileMixin`). Permissions come from the
permission backend: members may read (`view_profile_members`), managing takes
`add_profileuserrole` / `change_profileuserrole` / `delete_profileuserrole` (the owner and
active admins by default).

| Endpoint | |
|---|---|
| `GET /profile-members` | Members (active and deactivated); `?role=`, `?status=`, `?q=` |
| `GET\|PATCH\|DELETE /profile-members/{id}` | Read, change the role (`{"role": 1}`), remove |
| `POST /profile-members/{id}/deactivate`, `/reactivate` | Change access |
| `GET /profile-invitations` | Invitations, all statuses; `?status=`, `?role=`, `?q=` |
| `POST /profile-invitations` | `{"emails": [...], "invitations": [{"email", "first_name", "last_name"}], "role": 2, "message": ""}` |
| `GET /profile-invitations/{id}`, `POST .../resend`, `POST .../cancel` | |
| `GET /profile-invitations/by-token/{token}` | Public summary (no sign-in, rate-limited) |
| `POST /profile-invitations/by-token/{token}/accept`, `/decline` | Signed-in invitee |
| `POST /profile-invitations/by-token/{token}/accept-with-signup` | `{"password", "first_name", "last_name"}` (no sign-in, rate-limited, opt-in) |

Choices are serialized as their keys (`role`, `status` are integers). A refused operation
answers `{"non_field_errors": ["..."], "code": "<error code>"}` with 400 — or 404
(`invalid_token`), 403 (`signup_disabled`, `wrong_user`, `account_inactive`) or 409
(`user_exists`).

## Permissions

Subclass `ProfilesPermissionsBackend` to customize permissions, then replace the plugin entry in `AUTHENTICATION_BACKENDS` with your subclass:

```python
from baseapp_profiles.permissions import ProfilesPermissionsBackend


class MyProfilesPermissionsBackend(ProfilesPermissionsBackend):
    def has_perm(self, user_obj, perm, obj=None):
        return super().has_perm(user_obj, perm, obj)
```

```python
AUTHENTICATION_BACKENDS = [
    # ...
    # *plugin_registry.get("AUTHENTICATION_BACKENDS", "baseapp_profiles"),
    "myapp.permissions.MyProfilesPermissionsBackend",
    # ...
]
```

## How to develop

General development instructions can be found in the [main README](../README.md#how-to-develop).

### Prerequisites when activating `baseapp_profiles`

Because the models are abstract + swappable with no concrete models shipped, create a local app (we suggest `apps/social/profiles/`) implementing the concrete models:

```python
from baseapp_profiles.models import AbstractProfile, AbstractProfileUserRole


class Profile(AbstractProfile):
    class Meta(AbstractProfile.Meta):
        pass


class ProfileUserRole(AbstractProfileUserRole):
    class Meta(AbstractProfileUserRole.Meta):
        pass
```

Then point swapper at them:

```python
BASEAPP_PROFILES_PROFILE_MODEL = "profiles.Profile"
BASEAPP_PROFILES_PROFILEUSERROLE_MODEL = "profiles.ProfileUserRole"
```

### Upgrading to invitation history and ownerless profiles

Run `./manage.py makemigrations` for your profiles app: `Profile.owner` becomes nullable,
`ProfileUserRole` gains the invitation and audit fields and the CANCELLED status, and the
`(user, profile)` and `(profile, invited_email)` uniqueness becomes conditional on open
rows. Behaviour stays as it was until you turn on the settings above. Code that compares
`profile.owner_id` with a user id should switch to `profile.is_owned_by(user)` before you
create ownerless profiles.

### Migrating an existing project

If your project had profiles before adopting `baseapp_profiles`, follow [`MIGRATION.md`](MIGRATION.md) for extending your model from `ProfilableModel` and backfilling profiles from the legacy data.
