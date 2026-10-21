# BaseApp Organizations

Reusable app that adds an `Organization` entity — a `ProfilableModel`, so each organization gets its own `Profile` (name, avatar, URL handle, members/roles) and can act as the actor/target of follows, blocks, comments, chats, etc. just like a user.

`baseapp_organizations` follows the [plugin architecture](../baseapp_core/plugins/README.md): it registers itself as a plugin for settings aggregation and wires its permissions backend and GraphQL roots through the registry — no direct cross-package imports. It builds on [`baseapp_profiles`](../baseapp_profiles/README.md) (a required dependency).

## How to install

Install the package with `pip install baseapp-backend`.

If you want to develop, [install using this other guide](#how-to-develop).

## How to setup

The package registers itself as a plugin (see `baseapp_organizations.plugin:OrganizationsPlugin`), so most wiring goes through `plugin_registry`.

1. Add `baseapp_organizations` to `INSTALLED_APPS` (alongside `baseapp_profiles`, which it requires):

```python
INSTALLED_APPS = [
    # ...
    "baseapp_profiles",
    "baseapp_organizations",
    # ...
]
```

2. Wire the auth backend slot — `OrganizationsPermissionsBackend` is contributed via the registry:

```python
AUTHENTICATION_BACKENDS = [
    # ...
    *plugin_registry.get("AUTHENTICATION_BACKENDS", "baseapp_organizations"),
    # ...
]
```

3. Make sure your project's `graphql.py` composes the schema via `plugin_registry.get_all_graphql_*()` so `OrganizationsQueries` (`organization`) and `OrganizationsMutations` (`organizationCreate`) are picked up automatically.

4. Define the concrete `Organization` model (see [models](#models)) and point the swapper setting at it:

```python
BASEAPP_ORGANIZATIONS_ORGANIZATION_MODEL = "organizations.Organization"
```

Run `./manage.py makemigrations` / `./manage.py migrate` after defining it.

## Models

`AbstractOrganization` is abstract + swappable, and the package ships **no** concrete model or migrations — your project must subclass it and point the swapper setting at the concrete model (see [How to develop](#how-to-develop)).

| Abstract | Concrete reference | Purpose |
|---|---|---|
| `AbstractOrganization` | `Organization` | An organization entity. Fields: `name`. Inherits `ProfilableModel` (when `baseapp_profiles` is installed) + `DocumentIdMixin`. |

Because it's a `ProfilableModel`, `Organization` sets `profile_name_sql = "NEW.name"`, so the linked `Profile.name` is kept in sync by a DB trigger. It deliberately does **not** set `profile_owner_sql` — an organization's profile owner is determined by application logic, so the `Profile` is created and linked by the `organizationCreate` mutation (via the `profiles.graphql` shared service) or by [`OrganizationService`](#creating-organizations-outside-graphql) rather than by an INSERT trigger. See [`ProfilableModel`](../baseapp_profiles/README.md#profilablemodel) for the trigger contract.

## Creating organizations outside GraphQL

`organizationCreate` makes the signed-in user the owner of the new profile. Admin actions,
importers, data migrations and management commands use `OrganizationService` instead,
which always creates and links the profile and makes the owner optional:

```python
from baseapp_organizations.services import OrganizationService

organization = OrganizationService.create("Acme", url_path="acme-holdings")  # ownerless
organization = OrganizationService.create("Acme", owner=user)
OrganizationService.ensure_profile(organization)  # create the profile if it is missing
```

| | |
|---|---|
| `OrganizationService.create(name, *, owner=None, url_path=None, **fields)` | Create the organization (extra `fields` go to your concrete model) and its profile in one transaction. `url_path` sets the handle (a taken one gets a numeric suffix); otherwise it is derived from the name. |
| `OrganizationService.ensure_profile(organization, *, owner=None, url_path=None)` | Return the organization's profile, creating and linking one when it has none. |
| `ensure_profiles_for_organizations(queryset=None, *, owner=None)` | Give every organization without a profile one; returns how many were created. |

`ensure_profiles_for_organizations` is meant for the data migration of a project that
adopts organizations for existing rows:

```python
def backfill(apps, schema_editor):
    from baseapp_organizations.services import ensure_profiles_for_organizations

    ensure_profiles_for_organizations()


class Migration(migrations.Migration):
    dependencies = [("organizations", "0002_..."), ("profiles", "0007_...")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
```

It works on the current models rather than migration state (it needs `Profile.save()` to
create URL paths), so place it after the migrations that bring the profile and
organization tables to their current shape.

### Ownerless organizations

An organization created without an owner is run by its ADMIN members (see
[Members and invitations](../baseapp_profiles/README.md#members-and-invitations)). Its last
active admin cannot be demoted, deactivated or removed, and the `organizations.account`
service blocks that admin's account deletion until another member is made an admin.
Permission checks never treat an ownerless profile as owned by anyone.

The Django admin creates a missing profile with the saving staff user as owner, and leaves
an existing one (ownerless or not) alone; the DB trigger keeps its name in sync.

## GraphQL

### Queries (`OrganizationsQueries`)

| Field | Description |
|---|---|
| `organization(id)` | RelayNode fetch of a single `Organization`. `get_node` enforces `view_organization`. |

### Mutations (`OrganizationsMutations`)

| Field | Purpose |
|---|---|
| `organizationCreate` | Create an organization (requires `add_organization`). Accepts `name` and optional `url_path`; creates and links the organization's `Profile` through the `profiles.graphql` service and returns both the `organization` and `profile` edges. |

```graphql
mutation OrganizationCreateMutation($input: OrganizationCreateInput!) {
    organizationCreate(input: $input) {
        organization {
            node {
                id
                profile {
                    id
                    name
                    urlPath {
                        path
                    }
                }
            }
        }
        profile {
            node {
                id
            }
        }
        errors {
            field
            messages
        }
    }
}
```

`OrganizationObjectType` exposes `pk` and `profile`, and composes `PermissionsInterface`. Most organization data (name, avatar, members, follows, …) is read through the linked `Profile` and its interfaces.

## Shared services

### Consumed

- **`profiles.graphql`** (from `baseapp_profiles`) — `organizationCreate` calls `create_profile_from_mutation(...)` to create and link the organization's `Profile` (with `name` / `url_path`). When the service is unavailable the organization is still created, just without a profile.

### Provided

- **`organizations.account`** (`OrganizationAccountService`) — `get_account_deletion_block_reason(user)`, consumed by `baseapp_auth`'s delete-account endpoint: the owner of an organization, or the only active admin of an ownerless one, cannot delete their account.

### Required packages

- `baseapp_profiles` — `Organization` is a `ProfilableModel` and its profile is created via the profiles service.

## Permissions

`OrganizationsPermissionsBackend` grants `add_organization` to any authenticated user. Subclass it to customize, then replace the plugin entry in `AUTHENTICATION_BACKENDS` with your subclass:

```python
AUTHENTICATION_BACKENDS = [
    # ...
    # *plugin_registry.get("AUTHENTICATION_BACKENDS", "baseapp_organizations"),
    "myapp.permissions.MyOrganizationsPermissionsBackend",
    # ...
]
```

## How to develop

General development instructions can be found in the [main README](../README.md#how-to-develop).

### Prerequisites when activating `baseapp_organizations`

Because the model is abstract + swappable with no concrete model shipped, create a local app (we suggest `apps/organizations/`) implementing the concrete model:

```python
from baseapp_organizations.models import AbstractOrganization


class Organization(AbstractOrganization):
    class Meta(AbstractOrganization.Meta):
        pass
```

Then point swapper at it:

```python
BASEAPP_ORGANIZATIONS_ORGANIZATION_MODEL = "organizations.Organization"
```

Since `Organization` inherits `ProfilableModel`, run `makemigrations` to capture the profile-sync trigger SQL, then `migrate`.
