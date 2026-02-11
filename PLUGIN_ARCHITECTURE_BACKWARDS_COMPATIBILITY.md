# Plugin Architecture: Backward Compatibility and Rebase Guide

This document describes **what breaks** when rebasing a project onto the current BaseApp plugin architecture and **how to adapt**. We do **not** guarantee backward compatibility across this architectural change. The goal is to give a clear rebase plan so existing databases, settings, and coupling points can be migrated or stabilized.

**Related:** [PLUGIN_ARCHITECTURE.md](PLUGIN_ARCHITECTURE.md) — current architecture; this file is the companion for migration and compatibility.

---

## Table of Contents

1. [Stance on Backward Compatibility](#stance-on-backward-compatibility)
2. [Summary of Breaking Areas](#summary-of-breaking-areas)
3. [Database: Migrations and Table Ownership](#database-migrations-and-table-ownership)
4. [Database: Decoupling (DocumentId and Auxiliary Tables)](#database-decoupling-documentid-and-auxiliary-tables)
5. [Settings and Plugin Registry](#settings-and-plugin-registry)
6. [Coupled Points: Identification and Removal](#coupled-points-identification-and-removal)
7. [Compatibility Shims and Transitional Layers](#compatibility-shims-and-transitional-layers)

---

## Stance on Backward Compatibility

- **No backward compatibility guarantee** is made for the move to the current plugin architecture (registry-driven settings, DocumentId-based decoupling).
- **Existing database tables and migrations** can remain valid if you follow the rebase steps (e.g. `db_table`, manual data/schema migrations).
- **Coupled points** (imports, URLs/GraphQL schema, swapper settings, database) must be identified and either removed or aligned with the new patterns; this doc lists them and how to handle them.
- **Compatibility shims** are not part of the core design; if used, they should be short-lived and documented in your project.

---

## Summary of Breaking Areas

| Area | What breaks | How to adapt |
|------|-------------|--------------|
| **Database – plugin migrations** | Concrete models in plugin packages are removed; plugin migrations are deleted. | Use **swapper** so your app owns the models and migrations, or use **`db_table`** to keep using existing table names. |
| **Database – cross-app coupling** | Mixins like `CommentableModel` (and inline fields such as `comments_count`, `is_comments_enabled`) are removed; replaced by **CommentStats** (and similar) referencing **DocumentId**. | Add **manual migrations**: remove columns from your models, create/migrate auxiliary tables that reference `DocumentId`, backfill and wire signals. |
| **Settings** | `settings.py` is driven by **plugin registry** and **PackageSettings** (e.g. `INSTALLED_APPS`, slotted `MIDDLEWARE`, `AUTHENTICATION_BACKENDS`, `GRAPHENE__MIDDLEWARE`, Constance, extra settings). | Prefer adopting the registry pattern so future rebases stay smooth; optionally keep current settings short-term but **review and replace** registry-handled settings over time. |
| **URLs** | URL patterns are contributed via **PackageSettings** (`urlpatterns`, `v1_urlpatterns` callbacks) and collected with `plugin_registry.get_all_urlpatterns()` and `get_all_v1_urlpatterns()`. | **Replace** existing hardcoded BaseApp URL includes with `plugin_registry.get_all_urlpatterns()` and `plugin_registry.get_all_v1_urlpatterns()` in the project’s `urls.py`; do not duplicate plugin URLs manually. Plugins contribute via callbacks in `plugin.py`. |
| **GraphQL schema** | Queries, mutations, and subscriptions are contributed via **PackageSettings** (`graphql_queries`, `graphql_mutations`, `graphql_subscriptions`) and collected with `plugin_registry.get_all_graphql_queries()` etc. Optional GraphQL object-type interfaces are provided via **shared interface registry** by name. | **Review the root `graphql.py`**: remove all BaseApp app imports for Query/Mutation/Subscription mixins; use only the registry getters and project-specific mixins. Ensure each BaseApp package that should appear in the schema contributes `graphql_queries` / `graphql_mutations` / `graphql_subscriptions` in its `plugin.py`. For object-type interfaces (e.g. permissions, comments), use **`graphql_shared_interface_registry.get_interfaces([...], default_interfaces)`** by name so interfaces are pluggable; remove direct imports of other packages’ interface classes. |
| **Swapper** | Model identities (e.g. Comment, CommentStats, Page, Profile) are determined by **swapper** settings. | Keep `BASEAPP_*_*_MODEL` in settings pointing to your app’s concrete models; after DB decoupling, ensure new auxiliary models (e.g. CommentStats by DocumentId) are also swappable if the template uses them. |

---

## Database: Migrations and Table Ownership

### What changes

- Plugin packages **no longer ship concrete models that create tables in the plugin app**. Abstract/base models remain; **concrete models and their migrations are removed** from the plugin. So:
  - Any table that used to be created by a plugin migration (e.g. in `baseapp_pages`, `baseapp_comments` if they had any) will no longer be created by that package.
  - The **project** (or a dedicated app) is expected to own the schema: either by defining the concrete model and migrations in a local app (e.g. `testproject.pages`, `testproject.comments`) or by reusing the same table names and pointing the model at them.

### If you already use swapper (recommended)

- You already have **project-level apps** (e.g. `profiles.Profile`, `pages.Page`, `comments.Comment`) with their own migrations and tables.
- After rebase, the plugin only provides **abstract** models and no migrations; your app’s migrations continue to own the schema. **No change** to table ownership is required; ensure your swapper settings still point to your app labels and model names.

### If you do not use swapper and were relying on plugin migrations

- You need to **own** the schema in your project:
  1. **Create a local app** (or use an existing one) that defines the concrete model(s).
  2. **Keep the same table names** so existing data and any existing migrations (in your DB history) remain valid: use **`Meta.db_table`** to point to the previous table name (e.g. the one the plugin used).
  3. **Do not** rely on plugin migrations anymore; your app’s migrations are the single source of truth for those tables.

Example (conceptual): if the plugin used to create table `baseapp_pages_page`, your project model can do:

```python
class Page(AbstractPage):
    class Meta(AbstractPage.Meta):
        db_table = "baseapp_pages_page"  # or the actual historical name
```

Then your project’s migration should create the table with that name (or be a no-op if the table already exists from a previous install). New projects can use a different `db_table` or omit it and use the default.

### Summary

- **Existing tables remain valid** as long as some app defines a model with the same `db_table` (and compatible fields).
- **All “concrete” migrations in plugin packages are effectively deleted** from the template; the project is responsible for creating and evolving those tables.

---

## Database: Decoupling (DocumentId and Auxiliary Tables)

### What changes

- **Cross-package coupling at the DB level** is removed:
  - **CommentableModel** (mixin that added `comments_count`, `is_comments_enabled` and a `GenericRelation` to comments) is **removed** from models like Page/Profile.
  - **CommentStats** (and similar auxiliary concepts) no longer key off the commentable model directly; they key off **DocumentId**. So:
    - There is a **central DocumentId** row per “document” (e.g. per Page, per Profile).
    - **CommentStats** has a OneToOne (or FK) to **DocumentId** (e.g. `target_id` → `DocumentId.id`), not to the Page/Profile table.
  - Comment rows reference the commentable via **DocumentId** (or via `content_type`/`object_id` to the actual model; the architecture prefers going through DocumentId for consistency).

So: **schema and data migrations are required** wherever you previously had:
- Columns like `comments_count`, `is_comments_enabled` on your models, or
- Direct FKs from a plugin table into your app’s table (or the reverse).

### What you must do (manual migrations)

1. **Remove mixed-in columns from your models**
   - Create a migration that **drops** `comments_count`, `is_comments_enabled` (and any similar fields that came from CommentableModel or equivalent mixins) from your concrete models (e.g. Page, Profile).
   - This matches what the template does (e.g. `baseapp_pages` migration that removes those from Page).

2. **Ensure DocumentId exists for each “document”**
   - Models that are commentable (or otherwise need a document identity) should use **DocumentIdMixin** (or you must ensure a **DocumentId** row is created when the entity is created — e.g. via `DocumentId.get_or_create_for_object(instance)`). The template uses **DocumentIdMixin** + pgtrigger for this.

3. **Introduce or adjust auxiliary tables**
   - **CommentStats** (or your swapper equivalent) must be keyed by **DocumentId**, not by the commentable model. So:
     - Add a table (or change the existing one) so that it has a FK or OneToOne to `baseapp_core_documentid` (e.g. `target_id` as PK/FK to `DocumentId.id`).
     - Migrate existing data: for each previous “commentable” entity, get or create its **DocumentId**, then create/update the corresponding **CommentStats** row linked to that DocumentId.
   - Comment rows should reference the commentable via a stable identity; the template uses GenericForeignKey to the actual object; the “commentable” side is expressed via DocumentId for stats.

4. **Backfill DocumentId and auxiliary rows**
   - For existing rows that never had a DocumentId, use the core **backfill** command (or equivalent) so every relevant entity has a DocumentId. Then backfill CommentStats (and any other auxiliary tables) from existing data if you had denormalized counts or flags on the old model.

### Impact on other apps

- **Pages / Profiles / any commentable**
  - Lose `comments_count` and `is_comments_enabled` columns; comments data is obtained via **CommentStats** (and related tables) keyed by **DocumentId**.
- **Comments app**
  - Must create/update **CommentStats** rows keyed by **DocumentId** (e.g. on document creation and when comments are added/removed).
- **Reactions / Reports / Ratings / etc.**
  - If they follow a similar pattern (auxiliary table per “document”), they should also move to DocumentId-based auxiliary tables so that no package has FKs into another package’s tables. The same “manual migration + backfill” approach applies.

---

## Settings and Plugin Registry

### What changes

- **INSTALLED_APPS**, **MIDDLEWARE**, **AUTHENTICATION_BACKENDS**, **GRAPHENE__MIDDLEWARE**, **Constance** config, and various **extra settings** are intended to be **aggregated from plugins** via **PackageSettings** and **plugin_registry**.
- Projects can still **ignore** the registry and keep a fully hand-written `settings.py`, but then:
  - Future **rebases** may introduce new plugins or new settings keys; your settings won’t pick them up automatically and may drift or require repeated manual edits.
  - So the recommended path is to **review which settings are now registry-driven** and **replace** them step by step with the architecture pattern.

### Registry-driven settings (align with these)

- **INSTALLED_APPS** — `plugin_registry.get("INSTALLED_APPS")` (and optionally other fixed app lists).
- **MIDDLEWARE** — slotted: `plugin_registry.get("MIDDLEWARE", "slot_name")` so order is explicit and disabled plugins contribute nothing.
- **AUTHENTICATION_BACKENDS** — slotted: `plugin_registry.get("AUTHENTICATION_BACKENDS", "slot_name")`.
- **GRAPHENE__MIDDLEWARE** — slotted: `plugin_registry.get("GRAPHENE__MIDDLEWARE", "slot_name")`.
- **CONSTANCE_CONFIG** — merge project config with `plugin_registry.get_all_constance_config()`.
- **Extra key-value settings** — `plugin_registry.get_all_django_extra_settings()` and assign into your settings module (or merge into a dict).

### What to do

1. **Short term:** You can leave `settings.py` as-is so the app runs. Be aware that new plugins or new settings in the template may not appear in your project until you add them manually.
2. **Recommended:** Over time, **replace** the parts of `settings.py` that overlap with the registry (INSTALLED_APPS, MIDDLEWARE, AUTHENTICATION_BACKENDS, GRAPHENE middleware, Constance, extra settings) with the **registry API** and **plugin.py** contributions from each BaseApp package. That keeps you aligned with the architecture and makes future rebases easier.

---

## Coupled Points: Identification and Removal

These are the main coupling points that the new architecture changes or removes. Use this as a checklist.

### 1. Imports between packages

- **Old:** Direct imports from one BaseApp package into another for runtime behavior (e.g. “get comments count” by importing from baseapp_comments).
- **New:** No direct cross-package imports for behavior; use **DocumentId** and project-specific wiring.
- **Action:** Audit imports; replace with lookups or updates that don’t require cross-package imports. Keep only “contract” imports (e.g. baseapp_core models, swapper for model classes when defining FKs).

### 2. URLs

- **Old:** Hardcoded URL includes (e.g. `include("baseapp_auth.urls")`) in the project’s `urls.py`.
- **New:** Plugins contribute **urlpatterns** and **v1_urlpatterns** as **callables** in **PackageSettings**. The project uses `plugin_registry.get_all_urlpatterns()` and `plugin_registry.get_all_v1_urlpatterns()`.
- **Action:** Replace existing BaseApp URL includes with `*plugin_registry.get_all_urlpatterns()` and `*plugin_registry.get_all_v1_urlpatterns()` in the project’s `urls.py`. Do not duplicate or hand-wire plugin URLs manually. Each plugin contributes via callbacks in `plugin.py`.

### 3. GraphQL schema and shared interfaces

- **Old:** Root `graphql.py` (or equivalent) imports Query/Mutation/Subscription mixins from BaseApp packages (e.g. `ProfilesQueries`, `ChatsMutations`). Object types import interface classes from other packages (e.g. `PermissionsInterface` from `baseapp_auth`).
- **New:** Root **`graphql.py`** must **not** import BaseApp app mixins. Use only `plugin_registry.get_all_graphql_queries()`, `get_all_graphql_mutations()`, `get_all_graphql_subscriptions()`; add project-specific mixins (e.g. `UsersQueries`) if needed. Each BaseApp package that should appear in the schema contributes `graphql_queries` / `graphql_mutations` / `graphql_subscriptions` in its **plugin.py**. For **object-type interfaces** (e.g. permissions, comments), consumers use **`graphql_shared_interface_registry.get_interfaces(["permissions", "comments"], default_interfaces)`** by name; providers register in `AppConfig.ready()` via `GraphQLContributor`. No direct imports of other packages’ interface classes — interfaces are pluggable.
- **Action:** **Review the root `graphql.py`**: remove all BaseApp imports for schema mixins; build Query/Mutation/Subscription from registry getters and project mixins only. Ensure each plugin that should contribute to the schema has `graphql_queries` / `graphql_mutations` / `graphql_subscriptions` in its `plugin.py`. In object types that need optional interfaces (e.g. Page, Profile), replace direct interface imports with `graphql_shared_interface_registry.get_interfaces([...], default_interfaces)` so interfaces are loaded from the registry and remain pluggable.

### 4. Swapper

- **Old:** Same idea — project sets which concrete model implements Profile, Comment, Page, etc.
- **New:** Same; keep using swapper for model identity. After DocumentId decoupling, CommentStats may be swappable and point to a model that has `target` → DocumentId.
- **Action:** No structural change; keep settings like `BASEAPP_COMMENTS_COMMENTSTATS_MODEL = "comments.CommentStats"` and ensure the concrete model matches the new schema (DocumentId-based if the template moved there).

### 5. Database (already covered above)

- **Removed:** CommentableModel mixin, inline comment fields, direct FKs from plugin tables into your app’s tables.
- **Added:** DocumentId per document; auxiliary tables (e.g. CommentStats) keyed by DocumentId; manual migrations and backfills.

---

## Compatibility Shims and Transitional Layers

- The **core architecture does not ship compatibility shims** for the old inline commentable fields or plugin migration ownership. Rebase is a breaking change.
- **If you introduce shims in your project** (e.g. old settings keys mapped to the registry), they should be:
  - **Documented** in your repo (what they do and which consumers still depend on them).
  - **Time-bound**: plan to remove them after all consumers are migrated.
- **Recommended:** Prefer **direct migration** to the new patterns (registry, DocumentId, manual migrations) so you don’t carry long-lived compatibility code.

---

## Quick Rebase Checklist

- [ ] **Database – tables:** Confirm which tables were created by plugin migrations; move ownership to your app (swapper or `db_table`) and remove dependency on plugin migrations.
- [ ] **Database – decoupling:** Remove CommentableModel (and similar) columns via migrations; introduce DocumentId-based auxiliary tables (e.g. CommentStats); add backfill for DocumentId and for stats where needed.
- [ ] **Settings:** Replace INSTALLED_APPS / MIDDLEWARE / AUTHENTICATION_BACKENDS / GRAPHENE__MIDDLEWARE / Constance / extra settings with registry API and plugin.py where you want to align with the template.
- [ ] **URLs:** Replace existing BaseApp URL includes with plugin_registry.get_all_urlpatterns() and plugin_registry.get_all_v1_urlpatterns() in the project's urls.py; contribute urlpatterns/v1_urlpatterns (callbacks) from each plugin's plugin.py.
- [ ] **GraphQL schema:** Review root graphql.py: remove all BaseApp app imports for Query/Mutation/Subscription mixins; use plugin_registry.get_all_graphql_queries(), get_all_graphql_mutations(), get_all_graphql_subscriptions(); contribute graphql_queries/mutations/subscriptions from each plugin's plugin.py. Use graphql_shared_interface_registry.get_interfaces([...], default_interfaces) by name for pluggable object-type interfaces; no cross-package interface imports.
- [ ] **Swapper:** Keep model pointers correct; register new auxiliary models in admin if needed.
- [ ] **Imports:** Remove cross-package runtime imports where possible.
