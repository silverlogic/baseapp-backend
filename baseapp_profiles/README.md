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
| `AbstractProfile` | `Profile` | Public identity: `name` (trigger-maintained), `image`, `banner_image`, `biography`, `status` (public/private), `owner` FK, and a generic `target`. Inherits `DocumentIdMixin`, so any profile can be the target of follows/blocks/reports/comments/chats. |
| `AbstractProfileUserRole` | `ProfileUserRole` | Membership join row (`profile.members`): a user's `role` (manager/admin/…) and `status` (pending/active/…) on a profile. |

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
| `profileRoleUpdate` | Add/update a member's role/status on a profile. |
| `profileRemoveMember` | Remove a member from a profile. |

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

### Migrating an existing project

If your project had profiles before adopting `baseapp_profiles`, follow [`MIGRATION.md`](MIGRATION.md) for extending your model from `ProfilableModel` and backfilling profiles from the legacy data.
